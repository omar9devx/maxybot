# -*- coding: utf-8 -*-

# --- Standard Library Imports ---
import logging
import datetime
import traceback
import uuid
from typing import Optional

# --- Custom Formatter Class ---
class ErrorReportFormatter(logging.Formatter):
    """
    A custom logging formatter to create detailed, multi-line error reports.
    ينشئ تقرير خطأ مفصل ومنسق.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Formats the log record into a detailed error report."""
        
        # --- استخراج البيانات الإضافية أو وضع قيم افتراضية ---
        error_code = getattr(record, "error_code", uuid.uuid4().hex[:8])
        raw_data = getattr(record, "raw_data", "N/A")
        file_path = record.pathname
        folder, file_name = os.path.split(file_path)
        file_type = file_name.split('.')[-1]
        severity = getattr(record, "severity", "High")
        note = getattr(record, "note", "An unexpected error occurred.")
        possible_fix = getattr(record, "possible_fix", "Review the error details and traceback.")
        
        # --- استخراج نص الخطأ الكامل والـ Traceback ---
        if record.exc_info:
            error_type, error_value, tb = record.exc_info
            error_text = ''.join(traceback.format_exception(error_type, error_value, tb))
        else:
            error_text = record.getMessage()

        # --- تنسيق الوقت ---
        error_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

        # --- بناء تقرير الخطأ ---
        report = f"""
\r\n──────────────── ⚠️ ERROR REPORT ⚠️ ────────────────
error code   : [{error_code}]
error        : {error_text.strip()}
error data   : [{raw_data}]
file         : [{file_name}]
folder       : [{folder}]
type         : [{file_type}]
severity     : [{severity}]
note         : [{note}]
possible fix : [{possible_fix}]
error time   : [{error_time}]
─────────────────────────────────────────────────────\n
"""
        return report

# --- دالة إعداد الـ Logger ---
def setup_logger() -> logging.Logger:
    """Sets up the global logger with custom formatting and handlers."""
    
    logger = logging.getLogger('MaxyBotLogger')
    logger.setLevel(logging.ERROR)

    formatter = ErrorReportFormatter()

    # --- إعداد الحفظ في ملفين ---
    # File 1: errors.log
    log_handler = logging.FileHandler('errors.log', mode='a', encoding='utf-8')
    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)

    # File 2: errors.txt
    txt_handler = logging.FileHandler('errors.txt', mode='a', encoding='utf-8')
    txt_handler.setFormatter(formatter)
    logger.addHandler(txt_handler)

    # --- إعداد الطباعة في الـ Console ---
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # منع الـ logger من إرسال الأحداث إلى الـ root logger
    logger.propagate = False

    return logger