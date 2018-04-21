#!/usr/bin/env python3
# coding=utf-8

import io
import platform
import re
import time

import requests
from PIL import Image, ImageFilter
from lxml import etree
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import Chrome as Driver
from selenium.webdriver.common.action_chains import ActionChains
import numpy as np
from peakutils.peak import indexes

part_width, part_height = 10, 58
lines = 2
grey_threshold = 120

position_pattern = re.compile(r'.*background-position: ([\d\-]*)px ([\d\-]*)px')
image_pattern = re.compile(r'background-image: url\("(.*)"\).*')
slice_pattern = re.compile(r'.*width: (\d*)px; height: (\d*)px;')


def get_disordered_image(style):
    url = image_pattern.match(style).group(1)
    file = io.BytesIO(requests.get(url).content)
    return Image.open(file)


def get_origin_image(html):
    styles = html.xpath('//div[@class="gt_cut_fullbg_slice"]/@style')
    disordered_image = get_disordered_image(styles[0])
    parts_per_line = len(styles) // lines
    total_width = part_width * parts_per_line
    total_height = part_height * lines
    origin_image = Image.new('RGB', (total_width, total_height))
    for idx, style in enumerate(styles):
        m = position_pattern.match(style)
        x_offset = int(m.group(1))
        y_offset = int(m.group(2))
        source_x = -x_offset
        source_y = -y_offset
        dest_x = (idx % parts_per_line) * part_width
        dest_y = idx // parts_per_line * part_height
        im_part = disordered_image.crop((source_x, source_y, source_x + part_width, source_y + part_height))
        origin_image.paste(im_part, (dest_x, dest_y))
    return origin_image


def get_image_to_verify(driver, drag, origin_image):
    action = ActionChains(driver)
    action.click_and_hold(drag).perform()
    time.sleep(1)
    image_to_verify = Image.open(io.BytesIO(driver.get_screenshot_as_png()))
    x = driver.execute_script('return $("div.gt_cut_fullbg")[0].getBoundingClientRect().left')
    y = driver.execute_script('return $("div.gt_cut_fullbg")[0].getBoundingClientRect().top')
    factor = 2 if platform.system() == 'Darwin' else 1
    return image_to_verify.crop(
        (x * factor, y * factor, (x + origin_image.width) * factor, (y + origin_image.height) * factor))


def get_slice(html):
    style = html.xpath('//div[@class="gt_slice gt_show"]/@style')[0]
    m = slice_pattern.match(style)
    return int(m.group(1)), int(m.group(2))


def slice_offset(origin_image, image_to_verify):
    filter_func = lambda x: 0 if x < grey_threshold else 255
    origin_image_grey = origin_image.filter(ImageFilter.FIND_EDGES).convert('L').point(filter_func)
    image_to_verify_grey = image_to_verify.filter(ImageFilter.FIND_EDGES).convert('L').point(filter_func)
    if platform.system() == 'Darwin':
        image_to_verify_grey = image_to_verify_grey.resize((origin_image.width, origin_image.height))
    origin_image_grey.show()
    image_to_verify_grey.show()

    x_diff = [0] * origin_image.width
    for i in range(origin_image.width - 1, -1, -1):
        diff_count = 0
        for j in range(origin_image.height - 1, -1, -1):
            if origin_image_grey.getpixel((i, j)) != image_to_verify_grey.getpixel((i, j)):
                diff_count += 1
        x_diff[i] = diff_count
    waves = indexes(np.array(x_diff), thres=7.0/max(x_diff), min_dist=20)
    print("waves:", ' '.join((str(x) for x in waves)))
    offset = waves[2] - waves[0]
    print('offset:', offset)
    return offset


if __name__ == '__main__':
    driver = Driver()
    driver.get('https://passport.bilibili.com/login')
    while True:
        try:
            drag = driver.find_element_by_css_selector('.gt_slider_knob.gt_show')
            break
        except NoSuchElementException as e:
            time.sleep(2)
            continue
    html = etree.HTML(driver.page_source)
    origin_image = get_origin_image(html)
    # origin_image.save('origin.png')
    image_to_verify = get_image_to_verify(driver, drag, origin_image)
    # image_to_verify.save('verify.png')
    slice_width, slice_height = get_slice(html)
    offset = slice_offset(origin_image, image_to_verify)
    action = ActionChains(driver)
    action.drag_and_drop_by_offset(drag, offset, 0).perform()
