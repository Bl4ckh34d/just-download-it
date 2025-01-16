import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

class Logger:
    _instance: Optional['Logger'] = None
    
    def __init__(self):
        if Logger._instance is not None:
            raise RuntimeError("Logger is a singleton! Use Logger.get_instance()")
            
        # Create logs directory
        self.logs_dir = Path("logs")
        self.logs_dir.mkdir(exist_ok=True)
        
        # Configure root logger
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.DEBUG)
        
        # Console handler (INFO and above)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler (DEBUG and above, rotating)
        file_handler = RotatingFileHandler(
            self.logs_dir / "justdownloadit.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        Logger._instance = self
        
    @staticmethod
    def get_instance() -> logging.Logger:
        if Logger._instance is None:
            Logger()
        return Logger._instance.logger
        
    @staticmethod
    def get_logger(name: str) -> logging.Logger:
        """Get a named logger that inherits root logger settings"""
        return logging.getLogger(name)
