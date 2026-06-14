# hook_ssl.py
import os
import sys
import certifi

os.environ['SSL_CERT_FILE'] = os.path.join(
    sys._MEIPASS, 'certifi', os.path.basename(certifi.where())
)
os.environ['REQUESTS_CA_BUNDLE'] = os.environ['SSL_CERT_FILE']