import time
import random
import pandas as pd
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    WebDriverException
)

def setup_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    driver = webdriver.Chrome(options=options)
    return driver

def random_wait():
    wait_time = random.uniform(2, 5)
    time.sleep(wait_time)

def scrape_youtube_videos(url):
    if not url:
        return []
        
    driver = setup_driver()
    driver.get(url)
    random_wait()
    
    video_data = []
    scraped_videos = set()
    
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "contents")))
        
        while True:
            videos = driver.find_elements(By.XPATH, "//ytd-rich-item-renderer")
            
            for video in videos:
                try:
                    title_element = video.find_element(By.XPATH, ".//yt-formatted-string[@id='video-title']")
                    title = title_element.text
                    if title in scraped_videos:
                        continue
                        
                    views = video.find_element(By.XPATH, ".//span[@class='inline-metadata-item style-scope ytd-video-meta-block']").text
                    upload_date = video.find_elements(By.XPATH, ".//span[@class='inline-metadata-item style-scope ytd-video-meta-block']")[1].text
                    
                    video_info = {
                        "title": title,
                        "views": views,
                        "upload_date": upload_date
                    }
                    video_data.append(video_info)
                    scraped_videos.add(title)
                except NoSuchElementException:
                    continue
            
            last_height = driver.execute_script("return document.documentElement.scrollHeight")
            driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
            random_wait()
            new_height = driver.execute_script("return document.documentElement.scrollHeight")
            
            if new_height == last_height:
                break
                
    except TimeoutException:
        print("Timed out waiting for page elements to load")
    finally:
        driver.quit()
    
    # Ensure output directory exists
    os.makedirs('output', exist_ok=True)
    
    # Save data to Excel, CSV, and JSON
    if video_data:
        df = pd.DataFrame(video_data)
        df.to_excel("output/youtube_videos.xlsx", index=False)
        df.to_csv("output/youtube_videos.csv", index=False)
        
    return video_data