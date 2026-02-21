# ==================================================
# 💾 chat_store.py - Web UI 聊天历史 SQLite 存储
# ==================================================
# 提供对话和消息的 CRUD 操作
# 数据库文件：data/web_chat.db
# ==================================================

import sqlite3
import time
import uuid
import logging
import threading
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger("Fuguang.Web")


class ChatStore:
    """
    SQLite 聊天历史存储

    Tables:
        conversations: id, title, created_at, updated_at
        messages:      id, conversation_id, role, content, created_at
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()  # 线程本地连接

        # 确保目录存在 & 建表
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"💾 [ChatStore] 数据库已初始化: {db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self):
        """初始化数据库表"""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL DEFAULT '新对话',
                created_at  REAL NOT NULL,
                updated_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv
                ON messages(conversation_id, created_at);
        """)
        conn.commit()

    # ==================================================
    # 对话 CRUD
    # ==================================================

    def create_conversation(self, title: str = "新对话") -> Dict:
        """创建新对话，返回 {id, title, created_at, updated_at}"""
        conn = self._get_conn()
        conv_id = uuid.uuid4().hex[:12]
        now = time.time()
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, title, now, now)
        )
        conn.commit()
        return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}

    def list_conversations(self, limit: int = 50) -> List[Dict]:
        """获取最近的对话列表（按更新时间倒序）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str) -> Optional[Dict]:
        """获取单个对话"""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?",
            (conv_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_title(self, conv_id: str, title: str):
        """更新对话标题"""
        conn = self._get_conn()
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conv_id)
        )
        conn.commit()

    def delete_conversation(self, conv_id: str):
        """删除对话及其所有消息"""
        conn = self._get_conn()
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()

    # ==================================================
    # 消息 CRUD
    # ==================================================

    def add_message(self, conv_id: str, role: str, content: str) -> Dict:
        """添加消息并更新对话的 updated_at"""
        conn = self._get_conn()
        msg_id = uuid.uuid4().hex[:12]
        now = time.time()
        conn.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, conv_id, role, content, now)
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conv_id)
        )
        conn.commit()
        return {"id": msg_id, "role": role, "content": content, "created_at": now}

    def get_messages(self, conv_id: str) -> List[Dict]:
        """获取某对话的所有消息（按时间正序）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
            (conv_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def auto_title(self, conv_id: str, first_message: str):
        """根据第一条消息自动生成标题（截取前 20 字符）"""
        title = first_message.strip()[:20]
        if len(first_message.strip()) > 20:
            title += "..."
        self.update_title(conv_id, title)
