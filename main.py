import datetime as dt
import dateutil.tz
import json
import os
import time
import pathlib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

import boto3
import pygal
import pygal.style
import selenium.webdriver
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.common.by import By


TIMEOUT = 10
HOURLY_PATH = 'downloads/hourly/'
HOURLY_YESTERDAY_PATH = 'downloads/hourly_yesterday/'
DAILY_PATH = 'downloads/daily/'

SES_REGION = os.environ.get('ENEOS_DENKI_SES_REGION', None)
MAIL_FROM = os.environ.get('ENEOS_DENKI_MAIL_FROM', None)
MAIL_TO = os.environ.get('ENEOS_DENKI_MAIL_TO', None)
AWS_SESSION = boto3.Session(profile_name=os.environ.get('ENEOS_DENKI_AWS_PROFILE', None))


def plain_mail(subject, body):
    if not (SES_REGION and MAIL_FROM and MAIL_TO):
        return
    ses = AWS_SESSION.client('ses', SES_REGION)
    lvea = ses.list_verified_email_addresses()
    if MAIL_FROM not in lvea['VerifiedEmailAddresses']:
        print(f'Not Verified: {MAIL_FROM} in {lvea["VerifiedEmailAddresses"]}')
        return
    response = ses.send_email(
        Source=MAIL_FROM,
        Destination={'ToAddresses': MAIL_TO.split(',')},
        Message={'Subject': {'Data': subject}, 'Body': {'Text': {'Data': body}}},
    )
    return response


def mail(target_date, tmp_path):
    if not (SES_REGION and MAIL_FROM and MAIL_TO):
        return
    ses = AWS_SESSION.client('ses', SES_REGION)
    lvea = ses.list_verified_email_addresses()
    if MAIL_FROM not in lvea['VerifiedEmailAddresses']:
        print(f'Not Verified: {MAIL_FROM} in {lvea["VerifiedEmailAddresses"]}')
        return

    msg = MIMEMultipart('mixed')
    msg['Subject'] = f'[eneos-denki] {target_date.strftime("%Y-%m-%d")}'
    msg['From'] = MAIL_FROM
    msg['To'] = MAIL_TO
    msg_body = MIMEMultipart('alternative')
    textpart = MIMEText('画像'.encode('utf-8'), 'plain', 'utf-8')
    htmlpart = MIMEText(f'''
        <p><img src="cid:hourly"/></p>
        <p><img src="cid:daily"/></p>
    '''.encode('utf-8'), 'html', 'utf-8')
    msg_body.attach(textpart)
    msg_body.attach(htmlpart)
    msg.attach(msg_body)

    p = tmp_path + 'hourly.png'
    att = MIMEImage(open(p, 'rb').read(), 'png')
    att.add_header('Content-ID', '<hourly>')
    att.add_header('Content-Disposition','attachment', filename=os.path.basename(p))
    msg.attach(att)
    p = tmp_path + 'daily.png'
    att = MIMEImage(open(p, 'rb').read(), 'png')
    att.add_header('Content-ID', '<daily>')
    att.add_header('Content-Disposition','attachment', filename=os.path.basename(p))
    msg.attach(att)

    response = ses.send_raw_email(
        Source=MAIL_FROM,
        Destinations=MAIL_TO.split(','),
        RawMessage={'Data':msg.as_string()},
    )
    return response


def download_files(target_date, selenium_options):
    start_time = time.time()
    options = selenium.webdriver.ChromeOptions()

    options.binary_location = selenium_options['binary_location']
    for arg in ('--headless', '--no-sandbox', '--single-process', '--disable-gpu', '--window-size=1280x1696', '--disable-application-cache', '--disable-infobars', '--hide-scrollbars', '--enable-logging', '--log-level=0', '--ignore-certificate-errors', '--homedir=/tmp', '--disable-dev-shm-usage'):
        options.add_argument(arg)

    driver = selenium.webdriver.Chrome(executable_path=selenium_options['executable_path'], options=options)
    driver.command_executor._commands['send_command'] = ('POST', '/session/$sessionId/chromium/send_command')

    def find_element(by, value):
        return Wait(driver, TIMEOUT).until(ec.presence_of_element_located((by, value)))

    def set_download_path(path):
        os.makedirs(path, exist_ok=True)
        driver.execute('send_command', {
            'cmd': 'Page.setDownloadBehavior',
            'params': {'behavior': 'allow', 'downloadPath': path}
        })

    driver.get('https://www.eneos-denki.jp/web/portal/login')

    find_element(By.ID, 'userId').send_keys(os.environ['ENEOS_DENKI_USER_ID'])
    find_element(By.ID, 'password').send_keys(os.environ['ENEOS_DENKI_USER_PASSWORD'])
    find_element(By.CLASS_NAME, 'addon-button1').click()

    find_element(By.NAME, '_AUPOPL0006_WAR_Assetportlet_btn7005').click()
    set_download_path(selenium_options['tmp_path'] + HOURLY_PATH)
    driver.execute_script(f'document.getElementById("targetDateTab1").value = "{target_date.strftime("%Y/%m/%d")}"')
    find_element(By.XPATH, '//*[@id="frmDoViewTab1"]//input[@type="submit"]').click()
    find_element(By.XPATH, '//*[@id="tab1"]//input[@onclick="ouputCsv(\'preHour\')"]').click()

    set_download_path(selenium_options['tmp_path'] + HOURLY_YESTERDAY_PATH)
    driver.execute_script(f'document.getElementById("targetDateTab1").value = "{(target_date - dt.timedelta(days=1)).strftime("%Y/%m/%d")}"')
    find_element(By.XPATH, '//*[@id="frmDoViewTab1"]//input[@type="submit"]').click()
    find_element(By.XPATH, '//*[@id="tab1"]//input[@onclick="ouputCsv(\'preHour\')"]').click()

    find_element(By.ID, 'ui-id-2').click()
    set_download_path(selenium_options['tmp_path'] + DAILY_PATH)
    driver.execute_script(f'document.getElementById("targetDateTab3").value = "{target_date.strftime("%Y%m")}"')
    find_element(By.XPATH, '//*[@id="frmDoViewTab3"]//input[@type="submit"]').click()
    find_element(By.XPATH, '//*[@id="tab3"]//input[@onclick="ouputCsv(\'preDay\')"]').click()

    def get_file_path(path):
        timeout_time = time.time() + TIMEOUT
        parent_path = pathlib.Path(path)
        while time.time() < timeout_time:
            for p in parent_path.glob('*.csv'):
                if p.stat().st_mtime > start_time:
                    return str(p)
            time.sleep(0.1)
        else:
            raise TimeoutError()

    driver.close()
    driver.quit()

    return {
        'hourly_path': get_file_path(selenium_options['tmp_path'] + HOURLY_PATH),
        'hourly_yesterday_path': get_file_path(selenium_options['tmp_path'] + HOURLY_YESTERDAY_PATH),
        'daily_path': get_file_path(selenium_options['tmp_path'] + DAILY_PATH),
    }


def load(path):
    with open(path, encoding='shift_jis') as f:
        lines = f.readlines()
    return [l.strip().split(',') for l in lines[1:] if not l.strip().endswith(',')]


def load_hourly_data(path):
    splits = load(path)
    return [{
        'date': dt.datetime.strptime(f'{s[2]} {s[3]}', '%Y/%m/%d %H:%M'),
        'kwh': float(s[5]),
    } for s in splits]


def load_daily_data(path):
    splits = load(path)
    return [{
        'date': dt.datetime.strptime(s[2], '%Y/%m/%d'),
        'kwh': float(s[3]),
    } for s in splits]


def create_charts(paths, date, tmp_path):
    hourly_data = load_hourly_data(paths['hourly_path'])
    hourly_yesterday_data = load_hourly_data(paths['hourly_yesterday_path'])
    daily_data = load_daily_data(paths['daily_path'])

    def xhour(index, x):
        return x['date'].strftime('%H') if index % 2 == 0 else None

    chart = pygal.Line(interpolate='cubic')
    chart.title = f'{date.strftime("%Y/%m/%d")} Hourly Data (kWh)'
    chart.x_labels = [xhour(i, x) for i, x in enumerate(hourly_data)]
    chart.add('KINOU', [x['kwh'] for x in hourly_data], fill=True, show_dots=False)
    chart.add('OTOTOI', [x['kwh'] for x in hourly_yesterday_data], show_dots=False)
    chart.render_to_png(tmp_path + 'hourly.png')

    chart = pygal.Bar(style=pygal.style.RedBlueStyle)
    chart.title = f'{date.strftime("%Y/%m")} Daily Data (kWh)'
    chart.x_labels = [x['date'].strftime('%d') for x in daily_data]
    chart.add(None, [x['kwh'] for x in daily_data], rounded_bars=5)
    chart.render_to_png(tmp_path + 'daily.png')


def main(event, context):
    yesterday = dt.datetime.now(tz=dateutil.tz.gettz('Asia/Tokyo')) - dt.timedelta(days=1)
    tmp_path = event.get('tmp_path', '/tmp/')
    selenium_options = {
        'executable_path': event.get('executable_path', '/opt/chromedriver'),
        'binary_location': event.get('binary_location', '/opt/headless-chromium'),
        'tmp_path': tmp_path,
    }
    try:
        paths = download_files(yesterday, selenium_options)
        create_charts(paths, yesterday, tmp_path)

        mail(yesterday, tmp_path)
    except Exception as e:
        plain_mail('[eneos-denki] error', str(e))
        raise e
        return json.dumps({'success': False})
    return json.dumps({'success': True}, ensure_ascii=False)


if __name__ == '__main__':
    response = main({
        'executable_path': '/usr/local/bin/chromedriver',
        'binary_location': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        'tmp_path': './tmp/',
    }, None)
    print(response)
