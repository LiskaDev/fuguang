"""
📧 邮件监控技能 (Email Monitor Skills)
职责：后台监控 QQ 邮箱，智能过滤垃圾邮件，重要邮件通过扶光语音/Toast 通知

工作流程：
1. 后台线程每 N 秒检查一次 QQ 邮箱（IMAP）
2. 两层过滤：Python 规则快速分类 → AI 精准分类
3. 垃圾邮件静默，重要邮件通过 mouth.speak() + _show_toast() 通知

配置要求（.env）：
- EMAIL_QQ = QQ邮箱地址
- EMAIL_AUTH_CODE = QQ邮箱授权码（非QQ密码，在QQ邮箱设置-账户中生成）
- EMAIL_CHECK_INTERVAL = 检查间隔（秒），默认 7200（2小时）

架构：
- _EmailMonitorWorker: 纯逻辑后台工作类（IMAP + 分类）
- EmailSkills: Mixin，挂载到 SkillManager，提供 Function Calling 工具
"""

import imaplib
import email
import smtplib
import time
import logging
import re
import json
import threading
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path

logger = logging.getLogger("Fuguang.Email")


# ============================================================
# 📧 后台邮件工作类（纯逻辑，不依赖 Mixin self）
# ============================================================

class _EmailMonitorWorker:
    """
    后台邮件监控工作线程
    
    设计原则：
    - 与 SkillManager 解耦，通过回调通知
    - 复用 Brain 的 LLM 客户端，不创建新实例
    - IMAP 连接每次检查时建立，检查完断开（避免长连接超时）
    """

    # ---- 垃圾邮件规则（增强版） ----
    
    # 垃圾关键词（标题/正文命中 2 个以上 → spam）
    SPAM_KEYWORDS = [
        # 原始列表
        "退订", "取消订阅", "unsubscribe",
        "优惠", "打折", "促销", "限时",
        "免费领取", "中奖", "恭喜", "点击查看",
        "营销", "广告", "推广",
        # 增强：中文电商/金融垃圾
        "优惠券", "折扣", "红包", "限时抢购", "秒杀",
        "会员", "积分", "兑换", "开通", "续费",
        "白条", "贷款", "理财", "投资", "信用卡",
        "招聘", "求职", "兼职",
        "抽奖", "免费试用", "立即领取",
        "sale", "discount", "offer", "deal",
        "newsletter", "weekly digest", "monthly update",
    ]
    
    # 重要邮件关键词（命中 1 个 → important）
    IMPORTANT_KEYWORDS = [
        "账单", "发票", "invoice", "bill", "payment",
        "offer letter", "面试", "interview", "合同", "contract",
        "紧急", "urgent", "重要", "important",
        "deadline", "截止", "到期",
        "verification", "verify", "验证码",
        "password", "密码", "安全",
        "shipping", "发货", "快递", "物流",
    ]
    
    # 垃圾发件人模式（命中任一 → spam）
    SPAM_SENDER_PATTERNS = [
        "noreply@", "no-reply@", "marketing@",
        "newsletter@", "promo@", "ads@",
        "notification@", "donotreply@",
        "mailer-daemon@", "bounce@",
    ]
    
    # 垃圾发件人域名黑名单（精准匹配域名后缀）
    SPAM_SENDER_DOMAINS = [
        "taobao.com", "jd.com", "tmall.com", "pinduoduo.com",
        "mail.alipay.com", "mail.10086.cn", "mail.189.cn",
        "mail.ctrip.com", "mail.meituan.com", "mail.ele.me",
        "edm.",  # 任何 edm. 开头的子域名
        "mail.qq.com",  # QQ邮件通知本身
        "amazonses.com", "sendgrid.net", "mailchimp.com",
        "mandrillapp.com", "mailgun.org",
    ]
    
    # VIP 发件人（直接 → important，可由用户自定义扩展）
    VIP_SENDERS = [
        # 用户可在此添加重要联系人
    ]

    def __init__(self, qq_email: str, auth_code: str, check_interval: int,
                 llm_client, on_notify_callback):
        """
        Args:
            qq_email: QQ邮箱地址
            auth_code: QQ邮箱授权码
            check_interval: 检查间隔（秒）
            llm_client: OpenAI 客户端（复用 Brain 的 DeepSeek client）
            on_notify_callback: 通知回调 fn(level, message) -> None
        """
        self.qq_email = qq_email
        self.auth_code = auth_code
        self.check_interval = check_interval
        self.client = llm_client
        self.on_notify = on_notify_callback
        
        # 已处理邮件 ID 持久化文件
        self._processed_file: Optional[Path] = None
        self._processed_ids: set = set()
        
        # 缓存上次检查结果（含垃圾邮件），便于用户追问“刚才那封邮件内容是什么”
        self._last_check_results: List[Dict] = []
        self._last_check_time: Optional[datetime] = None
        self._cache_file: Optional[Path] = None  # 缓存持久化文件
        
        # 用户自定义过滤规则（通过对话动态添加，持久化到 JSON）
        self._filter_config_file: Optional[Path] = None
        self.user_vip_senders: List[str] = []
        self.user_spam_keywords: List[str] = []
        self.user_important_keywords: List[str] = []
        self.user_spam_domains: List[str] = []
        
        # 运行标志
        self._running = False
    
    def set_processed_file(self, path: Path):
        """设置已处理 ID 的持久化路径"""
        self._processed_file = path
        self._load_processed_ids()
    
    def _load_processed_ids(self):
        """从磁盘加载已处理的邮件 ID"""
        if self._processed_file and self._processed_file.exists():
            try:
                data = json.loads(self._processed_file.read_text(encoding='utf-8'))
                self._processed_ids = set(data.get("ids", []))
                # 只保留最近 500 条，防止文件无限增长
                if len(self._processed_ids) > 500:
                    self._processed_ids = set(list(self._processed_ids)[-500:])
                logger.debug(f"📧 加载 {len(self._processed_ids)} 条已处理邮件 ID")
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 加载已处理 ID 失败: {e}")
                self._processed_ids = set()
    
    def _save_processed_ids(self):
        """持久化已处理的邮件 ID"""
        if self._processed_file:
            try:
                data = {"ids": list(self._processed_ids)[-500:]}
                self._processed_file.write_text(
                    json.dumps(data, ensure_ascii=False), encoding='utf-8'
                )
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 保存已处理 ID 失败: {e}")

    def set_cache_file(self, path: Path):
        """设置邮件内容缓存的持久化路径，并加载已有缓存"""
        self._cache_file = path
        self._load_cache()

    def _load_cache(self):
        """从磁盘加载邮件内容缓存"""
        if self._cache_file and self._cache_file.exists():
            try:
                data = json.loads(self._cache_file.read_text(encoding='utf-8'))
                self._last_check_results = data.get("emails", [])
                time_str = data.get("check_time")
                if time_str:
                    self._last_check_time = datetime.fromisoformat(time_str)
                logger.info(f"📧 加载 {len(self._last_check_results)} 封缓存邮件")
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 加载缓存失败: {e}")

    def _save_cache(self):
        """持久化邮件内容缓存（最多保留 20 封）"""
        if self._cache_file:
            try:
                # 只保留最近 20 封，防止文件过大
                emails_to_save = self._last_check_results[-20:]
                data = {
                    "check_time": self._last_check_time.isoformat() if self._last_check_time else None,
                    "emails": emails_to_save,
                }
                self._cache_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
                )
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 保存缓存失败: {e}")

    # ---- 过滤规则配置 ----

    def set_filter_config_file(self, path: Path):
        """设置过滤规则配置文件路径，并加载已有配置"""
        self._filter_config_file = path
        self._load_filter_config()

    def _load_filter_config(self):
        """从磁盘加载用户自定义过滤规则"""
        if self._filter_config_file and self._filter_config_file.exists():
            try:
                data = json.loads(self._filter_config_file.read_text(encoding='utf-8'))
                self.user_vip_senders = data.get("vip_senders", [])
                self.user_spam_keywords = data.get("spam_keywords", [])
                self.user_important_keywords = data.get("important_keywords", [])
                self.user_spam_domains = data.get("spam_domains", [])
                total = (len(self.user_vip_senders) + len(self.user_spam_keywords) 
                         + len(self.user_important_keywords) + len(self.user_spam_domains))
                if total > 0:
                    logger.info(f"📧 加载 {total} 条用户自定义过滤规则")
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 加载过滤配置失败: {e}")

    def _save_filter_config(self):
        """持久化用户自定义过滤规则"""
        if self._filter_config_file:
            try:
                data = {
                    "vip_senders": self.user_vip_senders,
                    "spam_keywords": self.user_spam_keywords,
                    "important_keywords": self.user_important_keywords,
                    "spam_domains": self.user_spam_domains,
                }
                self._filter_config_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
                )
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 保存过滤配置失败: {e}")

    def add_filter_rule(self, category: str, value: str) -> str:
        """添加一条过滤规则"""
        category_map = {
            'vip': ('user_vip_senders', 'VIP 发件人'),
            'spam_keyword': ('user_spam_keywords', '垃圾关键词'),
            'important_keyword': ('user_important_keywords', '重要关键词'),
            'spam_domain': ('user_spam_domains', '垃圾域名'),
        }
        if category not in category_map:
            return f"❌ 无效类别: {category}。可选: vip, spam_keyword, important_keyword, spam_domain"
        
        attr_name, label = category_map[category]
        target_list = getattr(self, attr_name)
        
        if value in target_list:
            return f"⚠️ 「{value}」已在{label}列表中"
        
        target_list.append(value)
        self._save_filter_config()
        return f"✅ 已添加{label}: 「{value}」"

    def remove_filter_rule(self, category: str, value: str) -> str:
        """删除一条过滤规则"""
        category_map = {
            'vip': ('user_vip_senders', 'VIP 发件人'),
            'spam_keyword': ('user_spam_keywords', '垃圾关键词'),
            'important_keyword': ('user_important_keywords', '重要关键词'),
            'spam_domain': ('user_spam_domains', '垃圾域名'),
        }
        if category not in category_map:
            return f"❌ 无效类别: {category}"
        
        attr_name, label = category_map[category]
        target_list = getattr(self, attr_name)
        
        if value not in target_list:
            return f"⚠️ 「{value}」不在{label}列表中"
        
        target_list.remove(value)
        self._save_filter_config()
        return f"✅ 已删除{label}: 「{value}」"

    def list_filter_rules(self) -> str:
        """列出所有用户自定义的过滤规则"""
        lines = ["📧 邮件过滤规则配置:\n"]
        
        lines.append(f"⭐ VIP 发件人（直接标记为重要）:")
        if self.user_vip_senders:
            for v in self.user_vip_senders:
                lines.append(f"  - {v}")
        else:
            lines.append(f"  (未设置)")
        
        lines.append(f"\n🚨 重要关键词（命中即为重要）:")
        builtin_imp = ', '.join(self.IMPORTANT_KEYWORDS[:5]) + '...'
        lines.append(f"  内置: {builtin_imp}")
        if self.user_important_keywords:
            lines.append(f"  自定义: {', '.join(self.user_important_keywords)}")
        
        lines.append(f"\n🗑️ 垃圾关键词（命中 2 个以上即为垃圾）:")
        builtin_spam = ', '.join(self.SPAM_KEYWORDS[:5]) + '...'
        lines.append(f"  内置: {builtin_spam}")
        if self.user_spam_keywords:
            lines.append(f"  自定义: {', '.join(self.user_spam_keywords)}")
        
        lines.append(f"\n🚫 垃圾域名黑名单:")
        builtin_domains = ', '.join(self.SPAM_SENDER_DOMAINS[:5]) + '...'
        lines.append(f"  内置: {builtin_domains}")
        if self.user_spam_domains:
            lines.append(f"  自定义: {', '.join(self.user_spam_domains)}")
        
        return '\n'.join(lines)

    # ---- IMAP 操作 ----

    def _connect(self) -> Optional[imaplib.IMAP4_SSL]:
        """连接到 QQ 邮箱 IMAP"""
        try:
            mail = imaplib.IMAP4_SSL('imap.qq.com', 993)
            mail.login(self.qq_email, self.auth_code)
            mail.select('INBOX')
            logger.info("✅ [邮件] 已连接到 QQ 邮箱")
            return mail
        except Exception as e:
            logger.error(f"❌ [邮件] 连接失败: {e}")
            return None

    def _disconnect(self, mail: imaplib.IMAP4_SSL):
        """断开连接"""
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass

    @staticmethod
    def _decode_header(header: str) -> str:
        """解码邮件头（处理中文等编码）"""
        if not header:
            return ""
        decoded_parts = decode_header(header)
        result = []
        for content, encoding in decoded_parts:
            if isinstance(content, bytes):
                try:
                    result.append(content.decode(encoding or 'utf-8'))
                except Exception:
                    result.append(content.decode('utf-8', errors='ignore'))
            else:
                result.append(str(content))
        return ''.join(result)

    @staticmethod
    def _html_to_text(html_content: str) -> str:
        """
        轻量级 HTML → 可读文本转换（零依赖）
        保留：链接 [text](url)、换行、列表项
        移除：style/script 标签内容、HTML 实体、隐藏跟踪像素
        """
        from html.parser import HTMLParser
        
        class _HTMLToText(HTMLParser):
            def __init__(self):
                super().__init__()
                self.result = []
                self._skip = False        # 跳过 style/script 内容
                self._link_href = None    # 当前链接 URL
                self._link_text = []      # 链接文字缓冲
                self._in_link = False
            
            def handle_starttag(self, tag, attrs):
                tag = tag.lower()
                attrs_dict = dict(attrs)
                
                if tag in ('style', 'script', 'head'):
                    self._skip = True
                    return
                
                # 跟踪像素（1x1 隐藏图片），跳过
                if tag == 'img':
                    width = attrs_dict.get('width', '')
                    height = attrs_dict.get('height', '')
                    if width in ('1', '0') or height in ('1', '0'):
                        return
                    alt = attrs_dict.get('alt', '')
                    if alt:
                        self.result.append(f'[图片: {alt}]')
                    return
                
                if tag == 'a':
                    self._in_link = True
                    self._link_href = attrs_dict.get('href', '')
                    self._link_text = []
                    return
                
                if tag == 'br':
                    self.result.append('\n')
                elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'tr'):
                    self.result.append('\n')
                elif tag == 'li':
                    self.result.append('\n• ')
                elif tag == 'td':
                    self.result.append(' | ')
            
            def handle_endtag(self, tag):
                tag = tag.lower()
                if tag in ('style', 'script', 'head'):
                    self._skip = False
                    return
                
                if tag == 'a':
                    link_text = ''.join(self._link_text).strip()
                    if self._link_href and link_text:
                        # 跳过 unsubscribe/tracking 链接
                        href_lower = self._link_href.lower()
                        if any(x in href_lower for x in ['unsubscribe', 'tracking', 'click.', 'open.']):
                            pass
                        else:
                            self.result.append(f'[{link_text}]({self._link_href})')
                    elif link_text:
                        self.result.append(link_text)
                    self._in_link = False
                    self._link_href = None
                    self._link_text = []
                    return
                
                if tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4'):
                    self.result.append('\n')
            
            def handle_data(self, data):
                if self._skip:
                    return
                if self._in_link:
                    self._link_text.append(data)
                else:
                    self.result.append(data)
            
            def handle_entityref(self, name):
                entity_map = {'nbsp': ' ', 'lt': '<', 'gt': '>', 'amp': '&', 'quot': '"'}
                char = entity_map.get(name, f'&{name};')
                if self._in_link:
                    self._link_text.append(char)
                else:
                    self.result.append(char)
            
            def handle_charref(self, name):
                try:
                    if name.startswith('x'):
                        char = chr(int(name[1:], 16))
                    else:
                        char = chr(int(name))
                    if self._in_link:
                        self._link_text.append(char)
                    else:
                        self.result.append(char)
                except (ValueError, OverflowError):
                    pass
            
            def get_text(self):
                text = ''.join(self.result)
                # 清理多余空行和空白
                text = re.sub(r'\n{3,}', '\n\n', text)
                text = re.sub(r' {2,}', ' ', text)
                return text.strip()
        
        parser = _HTMLToText()
        try:
            parser.feed(html_content)
            return parser.get_text()
        except Exception:
            # 解析失败时回退到简单正则
            text = re.sub(r'<[^>]+>', '', html_content)
            return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    def _extract_body_preview(msg, max_length=200) -> str:
        """
        提取邮件正文预览
        优先使用 text/plain，fallback 到 text/html（智能转换）
        """
        plain_body = ""
        html_body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                # 跳过附件
                if part.get('Content-Disposition', '').startswith('attachment'):
                    continue
                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    charset = part.get_content_charset() or 'utf-8'
                    decoded = payload.decode(charset, errors='ignore')
                    
                    if content_type == 'text/plain' and not plain_body:
                        plain_body = decoded
                    elif content_type == 'text/html' and not html_body:
                        html_body = decoded
                except Exception:
                    continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or 'utf-8'
                    decoded = payload.decode(charset, errors='ignore')
                    if msg.get_content_type() == 'text/html':
                        html_body = decoded
                    else:
                        plain_body = decoded
            except Exception:
                pass
        
        # 优先用纯文本，没有则转换 HTML
        if plain_body:
            body = plain_body
        elif html_body:
            body = _EmailMonitorWorker._html_to_text(html_body)
        else:
            return ""
        
        # 最终清理
        body = re.sub(r'\s+', ' ', body).strip() if max_length <= 200 else body.strip()
        return body[:max_length]

    def _fetch_email(self, mail: imaplib.IMAP4_SSL, email_id) -> Optional[Dict]:
        """获取单封邮件内容（含正文 + 附件信息）"""
        try:
            status, msg_data = mail.fetch(email_id, '(RFC822)')
            if status != 'OK':
                return None
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            subject = self._decode_header(msg.get('Subject', ''))
            from_addr = self._decode_header(msg.get('From', ''))
            date_str = msg.get('Date', '')
            preview = self._extract_body_preview(msg, max_length=200)
            full_body = self._extract_body_preview(msg, max_length=10000)
            
            # 提取附件信息
            attachments = self._extract_attachments(msg)
            
            return {
                'from': from_addr,
                'subject': subject,
                'preview': preview,
                'full_body': full_body,
                'date': date_str,
                'message_id': msg.get('Message-ID', ''),
                'attachments': attachments,
            }
        except Exception as e:
            logger.warning(f"⚠️ [邮件] 解析失败: {e}")
            return None

    @staticmethod
    def _extract_attachments(msg) -> List[Dict]:
        """
        提取邮件中的附件信息（文件名、类型、大小）
        
        Returns:
            附件列表 [{'filename': str, 'content_type': str, 'size': int}, ...]
        """
        attachments = []
        if not msg.is_multipart():
            return attachments
        
        for part in msg.walk():
            content_disposition = str(part.get('Content-Disposition', ''))
            
            # 跳过非附件部分
            if 'attachment' not in content_disposition and 'inline' not in content_disposition:
                continue
            
            # 跳过纯文本和 HTML 部分（通常是正文，不是附件）
            content_type = part.get_content_type()
            if content_type in ('text/plain', 'text/html') and 'attachment' not in content_disposition:
                continue
            
            filename = part.get_filename()
            if filename:
                filename = _EmailMonitorWorker._decode_header(filename)
            else:
                # 无文件名的附件，根据类型生成
                ext_map = {
                    'application/pdf': '.pdf',
                    'application/msword': '.doc',
                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
                    'application/vnd.ms-excel': '.xls',
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
                    'application/vnd.ms-powerpoint': '.ppt',
                    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
                    'application/zip': '.zip',
                    'image/png': '.png',
                    'image/jpeg': '.jpg',
                }
                ext = ext_map.get(content_type, '')
                filename = f'未命名附件{ext}'
            
            # 获取大小
            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0
            
            # 可读大小
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024*1024):.1f} MB"
            
            attachments.append({
                'filename': filename,
                'content_type': content_type,
                'size': size,
                'size_str': size_str,
            })
        
        return attachments

    # ---- 分类逻辑 ----

    def _classify_rule_based(self, email_data: Dict) -> str:
        """
        第一层：基于规则的快速分类（0 Token 消耗）
        合并内置规则 + 用户自定义规则
        
        Returns:
            'urgent' / 'important' / 'spam' / 'unknown'
        """
        sender = email_data['from'].lower()
        subject = email_data['subject'].lower()
        preview = email_data['preview'].lower()
        text = subject + " " + preview
        
        # 合并内置 + 用户规则
        all_vip = self.VIP_SENDERS + self.user_vip_senders
        all_spam_domains = self.SPAM_SENDER_DOMAINS + self.user_spam_domains
        all_important_kw = self.IMPORTANT_KEYWORDS + self.user_important_keywords
        all_spam_kw = self.SPAM_KEYWORDS + self.user_spam_keywords
        
        # 1. VIP 发件人 → important
        for vip in all_vip:
            if vip.lower() in sender:
                return 'important'
        
        # 2. 发件人域名黑名单 → spam
        for domain in all_spam_domains:
            if domain in sender:
                return 'spam'
        
        # 3. 发件人模式匹配 → spam
        for pattern in self.SPAM_SENDER_PATTERNS:
            if pattern in sender:
                return 'spam'
        
        # 4. 主题行特征
        if re.match(r'^.*验证码.*$', subject) and len(subject) < 30:
            return 'normal'
        if re.match(r'^(AD|广告|推广)', subject):
            return 'spam'
        
        # 5. 重要关键词 → important
        important_count = sum(1 for kw in all_important_kw if kw in text)
        if important_count >= 1:
            return 'important'
        
        # 6. 垃圾关键词（命中 2 个以上 → spam）
        spam_count = sum(1 for kw in all_spam_kw if kw in text)
        if spam_count >= 2:
            return 'spam'
        
        return 'unknown'

    def _classify_ai(self, email_data: Dict) -> str:
        """
        第二层：AI 快速分类（~100 Token）
        
        Returns:
            'urgent' / 'important' / 'normal' / 'spam'
        """
        # 无 LLM 客户端时直接降级为 normal
        if not self.client:
            return 'normal'
        
        try:
            prompt = f"""邮件快速分类（只输出数字1-4，不要其他内容）：

发件人：{email_data['from']}
标题：{email_data['subject']}
内容预览：{email_data['preview'][:100]}

分类标准：
1 = 紧急（需立即处理，如账单到期、面试通知、紧急工作）
2 = 重要（今天需要看，如工作邮件、重要通知、快递）
3 = 普通（可以晚点看，如订阅内容、一般通知）
4 = 垃圾（营销邮件、广告、推广、促销）

输出（只输出数字）："""
            
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=10,
                temperature=0.1
            )
            
            result = response.choices[0].message.content.strip()
            level_map = {'1': 'urgent', '2': 'important', '3': 'normal', '4': 'spam'}
            # 取第一个数字字符
            for ch in result:
                if ch in level_map:
                    return level_map[ch]
            return 'normal'
            
        except Exception as e:
            logger.warning(f"⚠️ [邮件] AI 分类失败: {e}")
            return 'normal'  # 失败时默认普通，宁可多报也别漏报

    # ---- 主逻辑 ----

    def check_once(self, include_spam: bool = False) -> List[Dict]:
        """
        执行一次邮箱检查
        
        Args:
            include_spam: 是否包含垃圾邮件在返回结果中（用于用户主动查看）
        
        Returns:
            邮件列表（已分级）
        """
        mail = self._connect()
        if not mail:
            return []
        
        results = []
        try:
            status, messages = mail.search(None, 'UNSEEN')
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()
            if not email_ids:
                logger.info("📭 [邮件] 没有新邮件")
                return []
            
            logger.info(f"📬 [邮件] 发现 {len(email_ids)} 封未读邮件，开始分类...")
            
            spam_count = 0
            for eid in email_ids:
                eid_str = eid.decode()
                
                # 跳过已处理
                if eid_str in self._processed_ids:
                    # 已处理过但仍未读 → 标记为已读
                    try:
                        mail.store(eid, '+FLAGS', '\\Seen')
                    except Exception:
                        pass
                    continue
                
                email_data = self._fetch_email(mail, eid)
                if not email_data:
                    continue
                
                # 第一层：规则分类
                level = self._classify_rule_based(email_data)
                
                # 第二层：规则无法判断时，用 AI
                if level == 'unknown':
                    level = self._classify_ai(email_data)
                
                email_data['level'] = level
                email_data['id'] = eid_str
                
                # 记录已处理
                self._processed_ids.add(eid_str)
                
                # ✅ 处理完毕 → 在 IMAP 中标记为已读
                try:
                    mail.store(eid, '+FLAGS', '\\Seen')
                except Exception as e:
                    logger.debug(f"⚠️ [邮件] 标记已读失败: {e}")
                
                if level == 'spam':
                    spam_count += 1
                    logger.debug(f"🗑️ [邮件] 垃圾过滤: {email_data['from']} - {email_data['subject'][:30]}")
                    if include_spam:
                        results.append(email_data)  # 用户要看垃圾邮件时也返回
                    continue
                
                results.append(email_data)
            
            # 持久化已处理 ID
            self._save_processed_ids()
            
            # ✅ 缓存本次检查的所有结果（含垃圾），便于用户追问
            self._last_check_results = results
            self._last_check_time = datetime.now()
            self._save_cache()  # 持久化到磁盘
            
            non_spam = len(results) - (spam_count if include_spam else 0)
            logger.info(f"📧 [邮件] 检查完成: {non_spam} 封有效, {spam_count} 封垃圾已过滤")
            
        except Exception as e:
            logger.error(f"❌ [邮件] 检查失败: {e}")
        finally:
            self._disconnect(mail)
        
        return results

    def _generate_notification(self, email_data: Dict) -> Optional[str]:
        """
        根据邮件级别生成通知消息
        
        Returns:
            通知文本，或 None（不需要通知）
        """
        level = email_data['level']
        
        if level == 'spam':
            return None
        
        if level == 'normal':
            # 普通邮件只记录日志
            logger.info(f"📨 [邮件] 普通: {email_data['from']} - {email_data['subject'][:40]}")
            return None
        
        level_icon = {'urgent': '🚨', 'important': '⚠️'}
        icon = level_icon.get(level, '📧')
        
        if level == 'urgent':
            # 紧急邮件：尝试用 AI 总结
            try:
                summary_prompt = f"""总结这封邮件的核心内容（30字以内）：
标题：{email_data['subject']}
发件人：{email_data['from']}
内容：{email_data['preview']}
总结："""
                response = self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": summary_prompt}],
                    max_tokens=80,
                    temperature=0.3
                )
                summary = response.choices[0].message.content.strip()
                return f"{icon} 紧急邮件！{email_data['from']} - {summary}"
            except Exception:
                pass
        
        # important 或 urgent fallback
        return f"{icon} 新邮件: {email_data['from']} - {email_data['subject'][:50]}"

    def run_loop(self):
        """后台监控循环（在 daemon 线程中运行）"""
        logger.info(f"🚀 [邮件] 后台监控已启动，每 {self.check_interval} 秒检查一次")
        self._running = True
        
        # 首次启动延迟 30 秒，等系统完全初始化
        time.sleep(30)
        
        while self._running:
            try:
                new_emails = self.check_once()
                
                for email_data in new_emails:
                    msg = self._generate_notification(email_data)
                    if msg and self.on_notify:
                        self.on_notify(email_data['level'], msg)
                
            except Exception as e:
                logger.error(f"❌ [邮件] 监控循环异常: {e}")
            
            # 等待下次检查
            # 分段 sleep，方便快速停止
            for _ in range(self.check_interval):
                if not self._running:
                    break
                time.sleep(1)
        
        logger.info("⏹️ [邮件] 后台监控已停止")

    def search_emails(self, sender: str = '', keyword: str = '',
                      days_back: int = 7, max_results: int = 10) -> List[Dict]:
        """
        搜索邮件（支持按发件人/关键词/日期范围）
        
        Args:
            sender: 发件人关键词（模糊匹配）
            keyword: 标题关键词
            days_back: 搜索最近几天（默认7天）
            max_results: 最多返回几封（默认10）
        
        Returns:
            匹配的邮件列表
        """
        mail = self._connect()
        if not mail:
            return []
        
        results = []
        try:
            # 构建 IMAP SEARCH 条件
            criteria = []
            
            if sender:
                criteria.append(f'FROM "{sender}"')
            if keyword:
                criteria.append(f'SUBJECT "{keyword}"')
            if days_back > 0:
                since_date = (datetime.now() - timedelta(days=days_back)).strftime('%d-%b-%Y')
                criteria.append(f'SINCE {since_date}')
            
            # 默认搜索所有邮件（不限于未读）
            search_str = ' '.join(criteria) if criteria else 'ALL'
            
            status, messages = mail.search(None, search_str)
            if status != 'OK':
                return []
            
            email_ids = messages[0].split()
            if not email_ids:
                return []
            
            # 只取最近的 max_results 封
            email_ids = email_ids[-max_results:]
            
            logger.info(f"🔍 [邮件] 搜索到 {len(email_ids)} 封匹配邮件")
            
            for eid in email_ids:
                email_data = self._fetch_email(mail, eid)
                if not email_data:
                    continue
                
                email_data['level'] = self._classify_rule_based(email_data)
                email_data['id'] = eid.decode()
                results.append(email_data)
            
            # 本地二次过滤：IMAP FROM 只匹配邮箱地址，这里额外匹配显示名称（昵称）
            if sender and results:
                sender_lower = sender.lower()
                # 先检查是否所有结果都匹配（IMAP已匹配的情况）
                # 如果 IMAP 没找到结果但我们有缓存，可以搜索缓存
                filtered = [e for e in results if sender_lower in e['from'].lower()]
                if filtered:
                    results = filtered
            
            # 缓存搜索结果（可用 read_email 查看详情）
            if results:
                self._last_check_results = results
                self._last_check_time = datetime.now()
                self._save_cache()
            
        except Exception as e:
            logger.error(f"❌ [邮件] 搜索失败: {e}")
        finally:
            self._disconnect(mail)
        
        return results

    # ---- SMTP 发送 ----

    def send_reply(self, to_addr: str, subject: str, body: str,
                   original_message_id: str = '') -> bool:
        """
        通过 QQ 邮箱 SMTP 发送回复邮件
        
        Args:
            to_addr: 收件人邮箱
            subject: 邮件标题
            body: 邮件正文（纯文本）
            original_message_id: 原邮件 Message-ID（用于回复线程）
        
        Returns:
            是否发送成功
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.qq_email
            msg['To'] = to_addr
            msg['Subject'] = subject
            msg['Date'] = formatdate(localtime=True)
            msg['Message-ID'] = make_msgid(domain=self.qq_email.split('@')[1])
            
            # 回复线程关联
            if original_message_id:
                msg['In-Reply-To'] = original_message_id
                msg['References'] = original_message_id
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # QQ 邮箱 SMTP SSL
            with smtplib.SMTP_SSL('smtp.qq.com', 465) as smtp:
                smtp.login(self.qq_email, self.auth_code)
                smtp.send_message(msg)
            
            logger.info(f"✅ [邮件] 已发送回复到 {to_addr}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            logger.error("❌ [邮件] SMTP 认证失败: 授权码无效或已过期")
            return False
        except smtplib.SMTPRecipientsRefused:
            logger.error(f"❌ [邮件] 收件人地址无效: {to_addr}")
            return False
        except (smtplib.SMTPConnectError, ConnectionError, OSError) as e:
            logger.error(f"❌ [邮件] 连接 SMTP 服务器失败: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ [邮件] 发送失败（未知错误）: {e}")
            return False

    def reply_to_cached_email(self, index: int, reply_body: str) -> str:
        """
        回复缓存中的某封邮件
        
        Args:
            index: 邮件序号（从1开始）
            reply_body: 回复内容
        
        Returns:
            操作结果消息
        """
        if not self._last_check_results:
            return "❌ 没有缓存的邮件，请先检查或搜索邮箱"
        
        # 过滤非垃圾邮件
        non_spam = [e for e in self._last_check_results if e['level'] != 'spam']
        if not non_spam:
            non_spam = self._last_check_results
        
        if index < 1 or index > len(non_spam):
            return f"❌ 序号无效。缓存中共有 {len(non_spam)} 封邮件，请输入 1-{len(non_spam)}"
        
        em = non_spam[index - 1]
        
        # 提取回复地址（从 From 中提取纯邮箱地址）
        from_addr = em['from']
        # 处理 "Name <email@example.com>" 格式
        email_match = re.search(r'<([^>]+)>', from_addr)
        to_addr = email_match.group(1) if email_match else from_addr
        
        # 构造回复标题
        subject = em['subject']
        if not subject.lower().startswith('re:'):
            subject = f"Re: {subject}"
        
        # 构造回复正文（附上原文）
        original_preview = em.get('preview', '')[:200]
        full_reply = f"{reply_body}\n\n---\n原始邮件：\n发件人: {em['from']}\n日期: {em.get('date', '未知')}\n标题: {em['subject']}\n\n{original_preview}"
        
        success = self.send_reply(
            to_addr=to_addr,
            subject=subject,
            body=full_reply,
            original_message_id=em.get('message_id', '')
        )
        
        if success:
            return f"✅ 已回复邮件给 {to_addr}\n标题: {subject}"
        else:
            return f"❌ 回复发送失败，请检查网络和邮箱配置"

    def stop(self):
        """停止监控"""
        self._running = False


# ============================================================
# 📧 邮件技能 Mixin（挂载到 SkillManager）
# ============================================================

class EmailSkills:
    """
    邮件技能 Mixin
    
    提供：
    - _init_email_monitor(): 初始化并启动后台监控线程
    - check_email(): Function Calling 工具，手动触发一次邮件检查
    """

    # Function Calling Schema
    _EMAIL_TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "check_email",
                "description": (
                    "手动检查一次 QQ 邮箱的未读邮件。"
                    "默认会自动过滤垃圾邮件，只返回重要/普通邮件的摘要。"
                    "如果用户问「有没有新邮件」「查一下邮箱」等，使用此工具。"
                    "如果用户想看垃圾邮件，设置 include_spam=true。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "include_spam": {
                            "type": "boolean",
                            "description": "是否包含被过滤的垃圾邮件。默认false。"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_email",
                "description": (
                    "查看上次检查到的某封邮件的内容。"
                    "当用户问「邮件里面写了什么」「详细看看第X封」等时使用。"
                    "对于较长的邮件，默认只显示摘要。"
                    "如果用户明确要求看全文，设置 show_full=true。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "邮件序号（从1开始）。默认1。"
                        },
                        "show_full": {
                            "type": "boolean",
                            "description": "是否显示完整正文。默认false，只显示摘要。用户明确说「给我看全文」「展示完整内容」时设为true。"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "config_email_filter",
                "description": (
                    "配置邮件过滤规则。可以添加/删除 VIP 发件人、垃圾关键词、重要关键词、垃圾域名。"
                    "当用户说「把xxx添加为VIP」「把xxx加入垃圾名单」「查看过滤规则」等时使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["add", "remove", "list"],
                            "description": "操作类型。add=添加规则, remove=删除规则, list=查看所有规则"
                        },
                        "category": {
                            "type": "string",
                            "enum": ["vip", "spam_keyword", "important_keyword", "spam_domain"],
                            "description": "规则类别。vip=VIP发件人, spam_keyword=垃圾关键词, important_keyword=重要关键词, spam_domain=垃圾域名。list操作时可不填。"
                        },
                        "value": {
                            "type": "string",
                            "description": "要添加或删除的值（如邮箱地址、关键词、域名）。list操作时可不填。"
                        }
                    },
                    "required": ["action"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_email",
                "description": (
                    "搜索邮箱中的邮件。支持按发件人、标题关键词、日期范围搜索。"
                    "当用户说「找一下xx发的邮件」「上周有什么邮件」「搜索关于xx的邮件」等时使用。"
                    "搜索结果会替换缓存，可以用 read_email 查看详情。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sender": {
                            "type": "string",
                            "description": "发件人关键词（模糊匹配，如邮箱地址或名字）"
                        },
                        "keyword": {
                            "type": "string",
                            "description": "标题关键词"
                        },
                        "days_back": {
                            "type": "integer",
                            "description": "搜索最近几天的邮件。默认7（一周）。设为30搜索一个月。"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "最多返回几封。默认10。"
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "reply_email",
                "description": (
                    "回复之前查看过的某封邮件。"
                    "当用户说「回复那封邮件」「帮我回复说xxx」等时使用。"
                    "默认只显示回复预览，不会直接发送。"
                    "用户确认后，再次调用并设置 confirm=true 才会真正发送。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "index": {
                            "type": "integer",
                            "description": "要回复的邮件序号（从1开始）。默认1。"
                        },
                        "content": {
                            "type": "string",
                            "description": "回复内容（纯文本）"
                        },
                        "confirm": {
                            "type": "boolean",
                            "description": "是否确认发送。默认false（只预览）。用户明确说「确认发送」「发吧」时设为true。"
                        }
                    },
                    "required": ["content"]
                }
            }
        }
    ]

    def _init_email_monitor(self):
        """
        初始化邮件监控（在 BaseSkillMixin.__init__ 末尾调用）
        
        如果配置了邮箱信息，启动后台监控线程；
        否则静默跳过（不影响其他功能）。
        """
        self._email_worker: Optional[_EmailMonitorWorker] = None
        
        qq_email = getattr(self.config, 'EMAIL_QQ', '')
        auth_code = getattr(self.config, 'EMAIL_AUTH_CODE', '')
        
        if not qq_email or not auth_code:
            logger.info("📧 [邮件] 未配置邮箱信息，邮件监控已跳过")
            return
        
        check_interval = getattr(self.config, 'EMAIL_CHECK_INTERVAL', 7200)
        
        # 通知回调：通过扶光的嘴巴 + Toast 通知
        def _on_email_notify(level: str, message: str):
            try:
                # 系统 Toast 通知
                if hasattr(self, '_show_toast'):
                    self._show_toast("📧 扶光邮件提醒", message)
                
                # 语音通知（只对紧急和重要邮件）
                if level in ('urgent', 'important') and hasattr(self, 'mouth'):
                    # 语音要简短
                    short_msg = message[:60] if len(message) > 60 else message
                    self.mouth.speak(f"指挥官，你有新邮件。{short_msg}")
            except Exception as e:
                logger.warning(f"⚠️ [邮件] 通知发送失败: {e}")
        
        # 创建工作线程
        self._email_worker = _EmailMonitorWorker(
            qq_email=qq_email,
            auth_code=auth_code,
            check_interval=check_interval,
            llm_client=self.brain.client,
            on_notify_callback=_on_email_notify
        )
        
        # 设置持久化路径
        processed_file = self.config.DATA_DIR / "email_processed_ids.json"
        cache_file = self.config.DATA_DIR / "email_cache.json"
        filter_config_file = self.config.DATA_DIR / "email_filter_config.json"
        self._email_worker.set_processed_file(processed_file)
        self._email_worker.set_cache_file(cache_file)
        self._email_worker.set_filter_config_file(filter_config_file)
        
        # 启动后台线程
        email_thread = threading.Thread(
            target=self._email_worker.run_loop,
            name="EmailMonitor",
            daemon=True
        )
        email_thread.start()
        logger.info(f"✅ [邮件] 后台监控已启动 ({qq_email}, 每{check_interval}秒检查)")

    def check_email(self, include_spam: bool = False) -> str:
        """手动触发一次邮件检查。"""
        if not self._email_worker:
            return "❌ 邮件监控未启用（未配置 EMAIL_QQ 和 EMAIL_AUTH_CODE）"
        
        try:
            new_emails = self._email_worker.check_once(include_spam=include_spam)
            
            if not new_emails:
                # 没有新邮件，但有缓存 → 提示用户可以用 read_email 查看
                cached = self._email_worker._last_check_results
                if cached:
                    cache_time = self._email_worker._last_check_time
                    time_str = cache_time.strftime('%H:%M') if cache_time else '未知'
                    non_spam = [e for e in cached if e['level'] != 'spam']
                    hint = f"📭 没有新的未读邮件。\n\n上次检查（{time_str}）发现的 {len(non_spam)} 封邮件已缓存，"
                    hint += "可以用 read_email 查看具体内容。\n"
                    for i, em in enumerate(non_spam, 1):
                        hint += f"  {i}. {em['from']} - {em['subject'][:40]}\n"
                    return hint
                if include_spam:
                    return "📭 没有未读的垃圾邮件（之前检查过的邮件已标记为已读）"
                return "📭 没有新的重要邮件（垃圾邮件已自动过滤）"
            
            # 分离垃圾和非垃圾
            spam_list = [e for e in new_emails if e['level'] == 'spam']
            normal_list = [e for e in new_emails if e['level'] != 'spam']
            
            lines = []
            
            if normal_list:
                lines.append(f"📬 {len(normal_list)} 封新邮件：\n")
                for i, em in enumerate(normal_list, 1):
                    level_icon = {'urgent': '🚨', 'important': '⚠️', 'normal': '📨'}
                    icon = level_icon.get(em['level'], '📧')
                    lines.append(f"{i}. {icon} [{em['level']}] {em['from']}")
                    lines.append(f"   标题: {em['subject'][:60]}")
                    if em.get('attachments'):
                        att_names = ', '.join(a['filename'] for a in em['attachments'])
                        lines.append(f"   📎 附件: {att_names}")
                    if em['preview']:
                        lines.append(f"   预览: {em['preview'][:80]}")
                    lines.append("")
                lines.append("提示：可以用 read_email(序号) 查看某封邮件的完整内容。")
            
            if include_spam and spam_list:
                lines.append(f"\n🗑️ {len(spam_list)} 封垃圾邮件：\n")
                for i, em in enumerate(spam_list, 1):
                    lines.append(f"{i}. 🗑️ {em['from']}")
                    lines.append(f"   标题: {em['subject'][:60]}")
                    if em['preview']:
                        lines.append(f"   预览: {em['preview'][:80]}")
                    lines.append("")
            
            if not lines:
                return "📭 没有新邮件"
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"❌ [邮件] 手动检查失败: {e}")
            return f"❌ 邮件检查出错: {e}"

    def read_email(self, index: int = 1, show_full: bool = False) -> str:
        """
        查看上次检查到的某封邮件的内容。
        短邮件（≤500字）直接显示全文，长邮件默认只显示摘要。

        Args:
            index: 邮件序号（从1开始）
            show_full: 是否强制显示完整正文

        Returns:
            邮件内容
        """
        if not self._email_worker:
            return "❌ 邮件监控未启用"
        
        cached = self._email_worker._last_check_results
        if not cached:
            return "❌ 没有缓存的邮件记录。请先使用 check_email 检查邮箱。"
        
        # 过滤非垃圾邮件
        non_spam = [e for e in cached if e['level'] != 'spam']
        if not non_spam:
            non_spam = cached
        
        if index < 1 or index > len(non_spam):
            return f"❌ 序号无效。缓存中共有 {len(non_spam)} 封邮件，请输入 1-{len(non_spam)}。"
        
        em = non_spam[index - 1]
        cache_time = self._email_worker._last_check_time
        time_str = cache_time.strftime('%H:%M') if cache_time else '未知'
        
        level_icon = {'urgent': '🚨', 'important': '⚠️', 'normal': '📨', 'spam': '🗑️'}
        icon = level_icon.get(em['level'], '📧')
        
        lines = [
            f"{icon} 邮件详情（缓存于 {time_str}）",
            f"",
            f"发件人: {em['from']}",
            f"标  题: {em['subject']}",
            f"日  期: {em.get('date', '未知')}",
            f"分  级: {em['level']}",
        ]
        
        # 附件信息
        attachments = em.get('attachments', [])
        if attachments:
            lines.append(f"")
            lines.append(f"📎 附件 ({len(attachments)} 个):")
            for i, att in enumerate(attachments, 1):
                lines.append(f"  {i}. {att['filename']} ({att['size_str']}, {att['content_type']})")
        else:
            lines.append(f"📎 附件: 无")
        
        # 智能显示正文
        full_body = em.get('full_body', em.get('preview', '(无内容)'))
        body_length = len(full_body)
        
        if show_full or body_length <= 500:
            # 短邮件或用户要求全文 → 直接显示
            lines.append(f"")
            lines.append(f"--- 邮件正文 ({body_length}字) ---")
            lines.append(full_body)
        else:
            # 长邮件 → 只显示预览
            preview = em.get('preview', full_body[:200])
            lines.append(f"")
            lines.append(f"--- 邮件摘要 (全文{body_length}字) ---")
            lines.append(preview)
            lines.append(f"")
            lines.append(f"📝 邮件较长（{body_length}字），已显示摘要。如需查看全文，请说「给我看全文」。")
        
        return "\n".join(lines)

    def config_email_filter(self, action: str, category: str = '', value: str = '') -> str:
        """
        配置邮件过滤规则（VIP/垃圾关键词/重要关键词/垃圾域名）。

        Args:
            action: 'add' / 'remove' / 'list'
            category: 'vip' / 'spam_keyword' / 'important_keyword' / 'spam_domain'
            value: 要添加或删除的值

        Returns:
            操作结果
        """
        if not self._email_worker:
            return "❌ 邮件监控未启用"
        
        if action == 'list':
            return self._email_worker.list_filter_rules()
        elif action == 'add':
            if not category or not value:
                return "❌ 添加规则需要指定 category 和 value"
            return self._email_worker.add_filter_rule(category, value)
        elif action == 'remove':
            if not category or not value:
                return "❌ 删除规则需要指定 category 和 value"
            return self._email_worker.remove_filter_rule(category, value)
        else:
            return f"❌ 无效操作: {action}。可选: add, remove, list"

    def search_email(self, sender: str = '', keyword: str = '',
                     days_back: int = 7, max_results: int = 10) -> str:
        """
        搜索邮件（支持按发件人/关键词/日期范围）。

        Args:
            sender: 发件人关键词
            keyword: 标题关键词
            days_back: 搜索最近几天
            max_results: 最多返回几封

        Returns:
            搜索结果摘要
        """
        if not self._email_worker:
            return "❌ 邮件监控未启用"
        
        if not sender and not keyword:
            return "❌ 请至少提供发件人或关键词作为搜索条件"
        
        try:
            results = self._email_worker.search_emails(
                sender=sender, keyword=keyword,
                days_back=days_back, max_results=max_results
            )
            
            if not results:
                conditions = []
                if sender:
                    conditions.append(f"发件人含「{sender}」")
                if keyword:
                    conditions.append(f"标题含「{keyword}」")
                conditions.append(f"最近{days_back}天")
                return f"📭 未找到匹配的邮件（条件: {', '.join(conditions)}）"
            
            lines = [f"🔍 搜索到 {len(results)} 封邮件：\n"]
            for i, em in enumerate(results, 1):
                level_icon = {'urgent': '🚨', 'important': '⚠️', 'normal': '📨', 'spam': '🗑️'}
                icon = level_icon.get(em['level'], '📧')
                lines.append(f"{i}. {icon} {em['from']}")
                lines.append(f"   标题: {em['subject'][:60]}")
                lines.append(f"   日期: {em.get('date', '未知')[:20]}")
                if em.get('attachments'):
                    att_names = ', '.join(a['filename'] for a in em['attachments'])
                    lines.append(f"   📎 附件: {att_names}")
                lines.append("")
            
            lines.append("提示：可以用 read_email(序号) 查看某封邮件的完整内容。")
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"❌ [邮件] 搜索失败: {e}")
            return f"❌ 邮件搜索出错: {e}"

    def reply_email(self, index: int = 1, content: str = '', confirm: bool = False) -> str:
        """
        回复缓存中的某封邮件。
        默认只显示预览，confirm=True 时才真正发送。

        Args:
            index: 邮件序号（从1开始）
            content: 回复内容
            confirm: 是否确认发送

        Returns:
            操作结果
        """
        if not self._email_worker:
            return "❌ 邮件监控未启用"
        
        if not content:
            return "❌ 请提供回复内容"
        
        if confirm:
            # 用户确认 → 真正发送
            return self._email_worker.reply_to_cached_email(index=index, reply_body=content)
        else:
            # 预览模式 → 显示回复内容，等待确认
            cached = self._email_worker._last_check_results
            if not cached:
                return "❌ 没有缓存的邮件，请先检查邮箱"
            
            non_spam = [e for e in cached if e['level'] != 'spam']
            if not non_spam:
                non_spam = cached
            
            if index < 1 or index > len(non_spam):
                return f"❌ 序号无效。缓存中共有 {len(non_spam)} 封邮件"
            
            em = non_spam[index - 1]
            
            # 提取收件人地址
            from_addr = em['from']
            email_match = re.search(r'<([^>]+)>', from_addr)
            to_addr = email_match.group(1) if email_match else from_addr
            
            subject = em['subject']
            if not subject.lower().startswith('re:'):
                subject = f"Re: {subject}"
            
            lines = [
                "📧 回复预览（尚未发送）",
                "",
                f"收件人: {to_addr}",
                f"标  题: {subject}",
                f"",
                f"--- 回复内容 ---",
                content,
                f"",
                f"⚠️ 请确认以上内容无误。说「确认发送」或「发吧」将真正发出邮件。",
            ]
            return "\n".join(lines)

