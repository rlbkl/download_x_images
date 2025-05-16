#此脚本基于Grok V3 AI 开发
#此脚本仅用来学习交流，请勿用于非法事情，一切使用后果，由使用者承担，作者不承担任何责任
#使用此代码请遵守GPL V3协议(附加条款，禁止用于商业活动，或者谋取利益行为)

import os
import pickle
import time
import gc
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
#import pyautogui

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# 配置
TARGET_AUTHOR = "用户名"      # 目标作者的Twitter用户名
DOWNLOAD_DIR = TARGET_AUTHOR  # 图片下载目录
COOKIES_FILE = "cookies.json" # Cookies保存文件
MAX_THREADS = 10              # 最大下载线程数

# 创建下载目录
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# 初始化浏览器
driver = webdriver.Chrome()
# 设置窗口大小为 879x1133
#driver.set_window_size(879, 1133)
# 获取屏幕大小
#screen_width, screen_height = pyautogui.size()
# 将窗口定位到屏幕最右边，垂直居中
#window_x = screen_width - 879  # 屏幕宽度 - 窗口宽度
#window_y = (screen_height - 1133) / 2  # 屏幕高度 - 窗口高度，除以2
#driver.set_window_position(window_x, window_y)
#print(f"浏览器窗口已设置为 879x1133 像素，定位于屏幕最右边中间 (x={window_x}, y={window_y})")

# 检测是否已登录
def check_login():
    print("请在浏览器中手动登录Twitter（120秒内完成）...")
    driver.get("https://twitter.com/login")
    try:
        WebDriverWait(driver, 120).until(
            EC.presence_of_element_located((By.XPATH, "//article[@role='article']"))
        )
        print("检测到已登录！")
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        print(f"Cookies已保存到 {COOKIES_FILE}")
    except TimeoutException:
        print("登录超时，请在120秒内完成登录！")
        driver.quit()
        exit(1)

# 加载Cookies
def load_cookies():
    if os.path.exists(COOKIES_FILE):
        print("正在加载Cookies...")
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)
        driver.get("https://twitter.com")
        for cookie in cookies:
            driver.add_cookie(cookie)
        driver.refresh()
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//article[@role='article']"))
            )
            print("Cookies加载成功，已登录！")
            return True
        except TimeoutException:
            print("Cookies无效，将尝试重新登录...")
            return False
    return False

# 下载单张图片
def download_image(url, filepath, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, stream=True, timeout=10)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                print(f"已下载图片: {filepath}")
                return True
            else:
                print(f"下载图片失败: {url} (HTTP状态码: {response.status_code})，尝试 {attempt}/{max_retries}")
        except requests.RequestException as e:
            print(f"下载图片时出错: {url} ({e})，尝试 {attempt}/{max_retries}")
        time.sleep(1)
    return False

# 提取图片ID并构造高清URL
def get_image_info(img_url):
    try:
        img_id = img_url.split("/media/")[1].split("?")[0]
        png_url = f"https://pbs.twimg.com/media/{img_id}?format=png&name=large"
        jpg_url = f"https://pbs.twimg.com/media/{img_id}?format=jpg&name=large"
        return img_id, png_url, jpg_url
    except IndexError:
        print(f"无法解析图片URL: {img_url}")
        return None, None, None

# 处理单张图片的下载逻辑
def download_single_image(post_id, img_id, png_url, jpg_url, formatted_time):
    try:
        if formatted_time == "unknown":
            filename_base = f"{post_id}_{img_id}"
        else:
            filename_base = f"{formatted_time}_{post_id}_{img_id}"

        # 尝试下载PNG
        png_filepath = os.path.join(DOWNLOAD_DIR, f"{filename_base}.png")
        if download_image(png_url, png_filepath, max_retries=3):
            return True

        # PNG下载失败，尝试下载JPG
        jpg_filepath = os.path.join(DOWNLOAD_DIR, f"{filename_base}.jpg")
        if download_image(jpg_url, jpg_filepath, max_retries=3):
            return True

        # 两者都下载失败
        print(f"图片 {filename_base} 下载失败（PNG和JPG均失败）")

        # 询问用户是否继续尝试
        while True:
            user_input = input(f"图片 {filename_base} 6次尝试均失败，是否继续尝试下载？(y/n): ").strip().lower()
            if user_input == 'y':
                if download_image(png_url, png_filepath, max_retries=3):
                    return True
                elif download_image(jpg_url, jpg_filepath, max_retries=3):
                    return True
                else:
                    print(f"再次尝试下载 {filename_base} 失败")
            else:
                print(f"跳过图片 {filename_base}")
                return False
    except Exception as e:
        print(f"下载图片 {filename_base} 时出错: {e}")
        return False
    finally:
        # 确保文件句柄关闭
        gc.collect()

# 处理帖子
def process_posts():
    print("程序将自动模拟鼠标缓慢向下滑动，并处理新出现的帖子。\n")
    image_urls = []  # 存储图片信息：(post_id, img_id, png_url, jpg_url, formatted_time)
    processed_post_ids = set()  # 跟踪已处理的帖子ID
    processed_posts = 0
    no_new_posts_time = 0

    while True:
        try:
            # 模拟鼠标缓慢向下滑动，每0.5秒滑动400像素
            driver.execute_script("window.scrollBy(0, 400);")
            time.sleep(0.5)

            # 获取当前可见的帖子
            posts = driver.find_elements(By.XPATH, "//article[@role='article' and .//a[@role='link'][contains(@href, '/status/')]]")
            new_posts = 0
            for post in posts:
                try:
                    # 获取帖子ID
                    post_link = post.find_element(By.XPATH, ".//a[@role='link'][contains(@href, '/status/')]")
                    post_id = post_link.get_attribute("href").split("/")[-1]
                    if post_id not in processed_post_ids:
                        processed_post_ids.add(post_id)
                        processed_posts += 1
                        new_posts += 1
                        # 获取发布时间
                        try:
                            time_element = post.find_element(By.XPATH, ".//time")
                            post_time = time_element.get_attribute("datetime")
                            post_time_dt = datetime.strptime(post_time, "%Y-%m-%dT%H:%M:%S.%fZ")
                            formatted_time = post_time_dt.strftime("%Y_%m_%d_%H_%M")
                        except (NoSuchElementException, ValueError) as e:
                            print(f"无法获取帖子 {post_id} 的发布时间: {e}")
                            formatted_time = "unknown"
                        print(f"帖子 {processed_posts}: 发布时间 {formatted_time}\n")
                        # 检测是否为转帖
                        retweet_text = post.find_elements(By.XPATH, ".//span[contains(text(), '已转帖')]")
                        if retweet_text:
                            print(f"帖子 {processed_posts}: 检测到转帖，跳过\n")
                            continue
                        # 获取图片容器
                        image_containers = post.find_elements(By.XPATH, ".//div[@data-testid='tweetPhoto']")
                        if not image_containers:
                            print(f"帖子 {processed_posts}: 无图片\n")
                            continue
                        print(f"帖子 {processed_posts}: 找到 {len(image_containers)} 张图片\n")
                        for j, container in enumerate(image_containers, 1):
                            try:
                                img = container.find_element(By.XPATH, ".//img[@alt='图像']")
                                img_url = img.get_attribute("src")
                                img_id, png_url, jpg_url = get_image_info(img_url)
                                if img_id and png_url and jpg_url:
                                    image_urls.append((post_id, img_id, png_url, jpg_url, formatted_time))
                                    print(f"提取图片 {j}: ID为 {img_id}\n")
                                else:
                                    print(f"帖子 {processed_posts} 的第 {j} 张图片URL无效\n")
                            except (NoSuchElementException, StaleElementReferenceException):
                                print(f"帖子 {processed_posts} 的第 {j} 张图片未找到\n")
                except (StaleElementReferenceException, NoSuchElementException) as e:
                    print(f"处理帖子时出错: {e}\n")
                    continue
            if new_posts > 0:
                print(f"处理了 {new_posts} 个新帖子，总共 {processed_posts} 个帖子，收集到 {len(image_urls)} 张图片\n")
                no_new_posts_time = 0
            else:
                no_new_posts_time += 0.5
                if no_new_posts_time >= 10:
                    user_input = input("10秒内没有新帖子出现，是否继续？(y/n): ").strip().lower()
                    if user_input == 'y':
                        print("\n用户选择继续处理")
                        no_new_posts_time = 0
                    else:
                        print("退出处理。\n")
                        break
        except Exception as e:
            print(f"处理帖子时出错: {e}")
            time.sleep(2)
    return image_urls

# 下载所有收集的图片（多线程）
def download_images(image_urls):
    print(f"开始多线程下载 {len(image_urls)} 张图片...\n")
    downloaded_count = 0  # 统计成功下载的图片数
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        # 提交所有下载任务
        future_to_image = {
            executor.submit(download_single_image, post_id, img_id, png_url, jpg_url, formatted_time): (post_id, img_id)
            for post_id, img_id, png_url, jpg_url, formatted_time in image_urls
        }
        # 等待任务完成
        for future in as_completed(future_to_image):
            post_id, img_id = future_to_image[future]
            try:
                result = future.result()
                if result:
                    print(f"图片 {post_id}_{img_id} 下载成功")
                    downloaded_count += 1
                else:
                    print(f"图片 {post_id}_{img_id} 下载失败或被跳过")
            except Exception as e:
                print(f"图片 {post_id}_{img_id} 下载时发生异常: {e}")
    print(f"所有图片下载完成！共下载 {downloaded_count} 张图片")
    # 释放 DOWNLOAD_DIR 目录
    try:
        gc.collect()  # 强制垃圾回收，释放可能的未关闭句柄
        print(f"\n已释放目录 {DOWNLOAD_DIR}，可供其他程序访问")
    except Exception as e:
        print(f"释放目录 {DOWNLOAD_DIR} 时出错: {e}")
    return downloaded_count

# 主函数
def main():
    if not load_cookies():
        check_login()

    driver.get(f"https://twitter.com/{TARGET_AUTHOR}")
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//article[@role='article']")))
        print(f"已打开 {TARGET_AUTHOR} 的页面\n")
    except TimeoutException:
        print(f"无法加载 {TARGET_AUTHOR} 的页面，请检查网络或登录状态！")
        driver.quit()
        exit(1)

    # 处理帖子，收集图片URL
    image_urls = process_posts()

    if not image_urls:
        print("没有收集到任何图片，程序退出！")
        driver.quit()
        return

    # 下载所有图片
    download_images(image_urls)

    driver.quit()

if __name__ == "__main__":
    main()
