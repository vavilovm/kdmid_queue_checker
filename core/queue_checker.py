
import cv2
import numpy as np 
import pytesseract
import config
import time 
import datetime
import os
import json

import selenium
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

from webdriver_manager.chrome import ChromeDriverManager

import base64
from io import BytesIO
from PIL import Image

from core.image_processing import removeIsland

import logging
logging.basicConfig(filename='queue.log',
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.INFO)

pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_PATH



class QueueChecker: 
    def __init__(self):
        self.kdmid_subdomain = ''
        self.order_id = ''
        self.code = ''
        self.url = 'http://'+self.kdmid_subdomain+'.kdmid.ru/queue/OrderInfo.aspx?id='+self.order_id+'&cd='+self.code
        self.image_name = 'captcha_processed.png'
        self.screen_name = "screenshot0.png"
        self.button_dalee = "//input[@id='ctl00_MainContent_ButtonA']"
        self.button_inscribe = "//input[@id='ctl00_MainContent_ButtonB']"
        self.main_button_id = "//input[@id='ctl00_MainContent_Button1']" 
        self.text_form = "//input[@id='ctl00_MainContent_txtCode']"
        self.checkbox = "//input[@id='ctl00_MainContent_RadioButtonList1_0']" 
        self.error_code = "//span[@id='ctl00_MainContent_Label_Message']"
        # self.error_code = "//div[@class='error_msg']"
        self.captcha_error = "//span[@id='ctl00_MainContent_lblCodeErr']"

    def get_url(self, kdmid_subdomain, order_id, code):
        url = 'http://'+kdmid_subdomain+'.kdmid.ru/queue/OrderInfo.aspx?id='+order_id+'&cd='+code
        self.kdmid_subdomain = kdmid_subdomain
        self.order_id = order_id
        self.code = code     
        return url

    def write_success_file(self, text, status): 
        d ={}
        d['status'] = status
        d['message'] = text
        if d['status'] == 'success':
            with open(self.order_id+"_"+self.code+"_success.json", 'w', encoding="utf-8") as f:
                json.dump(d, f)
        elif d['status'] == 'error':
            with open(self.order_id+"_"+self.code+"_error.json", 'w', encoding="utf-8") as f:
                json.dump(d, f)    
        
    def check_exists_by_xpath(self, xpath, driver):
        mark = False
        try:
            driver.find_element(By.XPATH, xpath)
            mark = True
            return mark
        except NoSuchElementException:
            return mark
    
    def screenshot_captcha(self, driver, error_screen=None): 
		   # make a screenshot of the window, crop the image to get captcha only, 
		   # process the image: remove grey background, make letters black
        driver.save_screenshot("screenshot.png")
        
        screenshot = driver.get_screenshot_as_base64()
        img = Image.open(BytesIO(base64.b64decode(screenshot)))

        element = driver.find_element(By.XPATH, '//img[@id="ctl00_MainContent_imgSecNum"]')
        loc  = element.location
        size = element.size

        left = loc['x']
        top = loc['y']
        right = (loc['x'] + size['width'])
        bottom = (loc['y'] + size['height'])
        screenshot = driver.get_screenshot_as_base64()
		  #Get size of the part of the screen visible in the screenshot
        screensize = (driver.execute_script("return document.body.clientWidth"), 
		              driver.execute_script("return window.innerHeight"))
        img = img.resize(screensize)
        
        box = (int(left + 200), int(top), int(right - 200), int(bottom))
        area = img.crop(box)
        area.save(self.screen_name, 'PNG')
        
        img  = cv2.imread(self.screen_name)
        # Convert to grayscale
        c_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        # Median filter
        out = cv2.medianBlur(c_gray,1)
        # Image thresholding 
        a = np.where(out>150, 1, out)
        out = np.where(a!=1, 0, a)
        # Islands removing with threshold = 30
        out = removeIsland(out, 150)
        # Median filter
        out = cv2.medianBlur(out,3)

        # Cropping an image
        out = out[80:140, 5:195]

        cv2.imwrite(self.image_name, out*255)
        os.remove(self.screen_name)
        os.remove("screenshot.png")
    
    def recognize_image(self): 
        digits = pytesseract.image_to_string(self.image_name, config='--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789')
        return digits

    def check_queue(self, kdmid_subdomain, order_id, code): 
        message = ''
        status = ''
        print('Checking queue for: {} - {}'.format(order_id, code))
        logging.info('Checking queue for: {} - {}'.format(order_id, code))
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=chrome_options)
        driver.maximize_window()
        url = self.get_url(kdmid_subdomain, order_id, code)
        driver.get(url)
            
        error = True
        error_screen = False
        # iterate until captcha is recognized 
        while error: 
            self.screenshot_captcha(driver, error_screen)
            digits = self.recognize_image().strip()

            if (len(digits) != 6):
                status = 'error'
                message = f'Wrong digits length, digits: .{digits}.'

                print(message)

                self.write_success_file(str(message), str(status))
                logging.warning(f'{message}')

                driver.refresh()
                time.sleep(5)
                continue

            WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, self.text_form))).send_keys(str(digits))

            time.sleep(1)       
            # if the security code is wrong, expired or not from this order, stop the process
            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, self.error_code))
                )
                status = 'error'
                message = 'The security code {} is written wrong, has expired or is not from this order. Theck it and try again.'.format(self.code)
                
                self.write_success_file(str(message), str(status))	
                logging.warning(f'{message}')
                logging.warning(f'digits: {digits}')
                break
            except:
                logging.warning(f'Except digits: {digits}')

                pass

            if self.check_exists_by_xpath(self.button_dalee, driver): 
                driver.find_element(By.XPATH, self.button_dalee).click()

            if self.check_exists_by_xpath(self.button_inscribe, driver): 
                driver.find_element(By.XPATH, self.button_inscribe).click()

            window_after = driver.window_handles[0]
            driver.switch_to.window(window_after)

            error = False
            
            try: 
                driver.find_element(By.XPATH, self.main_button_id)    
            except: 
                error = True
                error_screen = True

                try:
                    element = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, self.text_form))
                    )
                except:
                    print("Element not found")

                driver.find_element(By.XPATH, self.text_form).clear()

        try: 
            if self.check_exists_by_xpath(self.checkbox, driver): 			
                driver.find_element(By.XPATH,self.checkbox).click()
                check_box = driver.find_element(By.XPATH, self.checkbox)
                val = check_box.get_attribute("value")
                message = 'Appointment date: {}, time: {}, purpose: {}'.format(
                    val.split('|')[1].split('T')[0], 
                    val.split('|')[1].split('T')[1], 
                    val.split('|')[-1]
                    )
                logging.info(message)
                WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.XPATH, self.main_button_id))).click()  
                status = 'success'         
                self.write_success_file(message, str(status))			
                
            else: 
                message = '{} - no free timeslots for now'.format(datetime.date.today())
                status = 'in process'
                print(message)
                logging.info(message)
        except: 
            message = '{} --- no free timeslots for now'.format(datetime.date.today())
            logging.info(message)

        time.sleep(5)

        driver.quit()
        if os.path.exists(self.screen_name):
            os.remove(self.screen_name)
        if os.path.exists(self.image_name):
            os.remove(self.image_name)         
              
        return message, status


# checker = QueueChecker()

# kdmid_subdomain = 'madrid' 
# order_id = '130238' 
# code = 'CD9E05C1' 

# 'madrid', '130238', 'CD9E05C1'
# 'madrid', '151321', '5CCF3A7C'
# checker.check_queue('madrid', '151321', '5CCF3A7C')

# print(res, sta)