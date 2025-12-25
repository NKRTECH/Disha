import logging
import json
import sys
import os
from datetime import datetime

# Check if running in serverless mode (read-only file system)
SERVERLESS_MODE = os.getenv("SERVERLESS_MODE", "false").lower() in ("true", "1", "yes")

class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    """
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "path": record.pathname
        }
        
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_record)

def setup_logger(name: str = "scraping_service", level: int = logging.INFO):
    """
    Setup and return a logger with JSON formatting
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding multiple handlers if setup_logger is called multiple times
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(JsonFormatter())
        logger.addHandler(console_handler)
        
        # File Handler - skip in serverless mode (read-only file system)
        if not SERVERLESS_MODE:
            try:
                file_handler = logging.FileHandler("scraping_service.log")
                file_handler.setFormatter(JsonFormatter())
                logger.addHandler(file_handler)
            except OSError:
                # Fallback: ignore file logging errors on read-only file systems
                pass
            
        
    return logger
