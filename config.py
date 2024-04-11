# -*- coding: utf-8 -*-
import os
if os.name == 'nt':
    TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
elif os.name == 'Darwin':
    TESSERACT_PATH = r'/usr/local/Cellar/tesseract/5.3.3/bin/tesseract'
else:
    TESSERACT_PATH = '/usr/bin/tesseract'