import logging
import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path

# Create a logger specifically for frontend requests
logger = logging.getLogger("frontend_requests")
logger.setLevel(logging.INFO)

# Define the log file path
log_file_path = Path("frontend_requests.log")

# Setup file handler
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)

# Setup a formatter
formatter = logging.Formatter('%(asctime)s - %(client_ip)s - %(method)s - %(url)s - %(status_code)s - %(process_time)sms')
file_handler.setFormatter(formatter)

# Add handler to the logger
logger.addHandler(file_handler)

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        process_time = (time.time() - start_time) * 1000
        client_ip = request.client.host if request.client else "unknown"
        
        # Log the iteration details
        logger.info(
            "Frontend iteration logged",
            extra={
                "client_ip": client_ip,
                "method": request.method,
                "url": str(request.url.path),
                "status_code": response.status_code,
                "process_time": f"{process_time:.2f}"
            }
        )
        
        return response
