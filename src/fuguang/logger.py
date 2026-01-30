import logging
import sys
from .config import LOG_DIR

def setup_logger():
    logger = logging.getLogger("Fuguang")
    logger.setLevel(logging.INFO)
    
    # Check if handlers already exist to avoid duplicate logs
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S'))
        logger.addHandler(console_handler)
        
        # File Handler
        file_handler = logging.FileHandler(LOG_DIR / "fuguang.log", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
    
    return logger

logger = setup_logger()
