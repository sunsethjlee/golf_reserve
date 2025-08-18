from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time

# ──────────────────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────────────────
chromedriver_path = "/path/to/chromedriver"  # TODO: 변경
SITE_URL = "https://example.com/reservation"  # TODO: 변경
LOGIN_URL = None  # 필요시 "https://example.com/login" 같이 입력

# 자정 실행 대기 (KST) 여부
RUN_AT_MIDNIGHT = False

# 우선순위: 성남 -> 수원
LOCATIONS = ["성남", "수원"]
COURSE_KEYWORDS = ["18홀"]

# 예약 오픈 범위: 금일 기준 +10 ~ +17
OPEN_RANGE_DAYS = (10, 17)

# 주말만 (토=5, 일=6)
WEEKEND_DAYS = {5, 6}

# 사이트별 XPATH / 텍스트 셀렉터 (TODO: 사이트 DOM에 맞게 채우세요)
XPATHS = {
    # 로그인 (옵션)
    "login_id":    "//input[@name='user_id']",
    "login_pw":    "//input[@name='password']",
    "login_btn":   "//button[contains(.,'로그인') or contains(.,'Login')]",

    # 캘린더 월 전환
    "cal_next":    "//*[@aria-label='next' or @id='calNext' or contains(@class,'next')]",  # 예시
    "cal_prev":    "//*[@aria-label='prev' or @id='calPrev' or contains(@class,'prev')]",

    # 날짜 셀 템플릿 (우선 data-date → 실패 시 텍스트 일자)
    # 아래 템플릿은 함수에서 format으로 대체
    "date_cell_data_date": "//*[@data-date='{yyyy}-{mm}-{dd}']",
    "date_cell_text":      "//*[contains(@class,'calendar')]//*[normalize-space(text())='{day}']",

    # 위치/코스/시간(텍스트 포함 요소 클릭)
    # 가능한 한 컨테이너 좁혀 주면 오클릭 줄어듦 (필요시 컨테이너 XPATH 추가)
    "location_text":  "//*[self::*='button' or self::*='a' or self::*='span' or self::*='div'][contains(normalize-space(), '{text}')]",
    "course_text":    "//*[self::*='button' or self::*='a' or self::*='span' or self::*='div'][contains(normalize-space(), '{text}')]",
    # 예약 가능 시간 버튼 (다국어/키워드 대응)
    "time_buttons":   "//button[not(@disabled) and (contains(.,'예약') or contains(.,'가능') or contains(.,'Available') or contains(.,'Book'))]",

    # 다음/확인/동의/제출
    "next_btn":       "//*[@id='nextBtn' or contains(.,'다음') or contains(.,'Next')]",
    "agree_checkbox": "//*[self::*='input' and @type='checkbox' or contains(@class,'agree')]",
    "confirm_btn":    "//*[self::*='button' and (contains(.,'확인') or contains(.,'결제') or contains(.,'예약완료') or contains(.,'Reserve'))]"
}

# 로그인 정보(사용자가 추후 직접 입력)
USER_ID = "<YOUR_ID>"      # TODO
USER_PW = "<YOUR_PASSWORD>"# TODO

# ──────────────────────────────────────────────────────────────────────────────
# 유틸 함수
# ──────────────────────────────────────────────────────────────────────────────
def kst_now():
    return datetime.now(ZoneInfo("Asia/Seoul"))

def get_target_weekend_dates():
    today = kst_now().date()
    start, end = OPEN_RANGE_DAYS
    dates = [today + timedelta(days=d) for d in range(start, end + 1)]
    return [d for d in dates if d.weekday() in WEEKEND_DAYS]

def wait_until_kst_midnight():
    now = kst_now()
    tomorrow = (now + timedelta(days=1)).date()
    midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=ZoneInfo("Asia/Seoul"))
    secs = (midnight - now).total_seconds()
    if secs > 0:
        print(f"[INFO] KST 자정까지 대기: {secs:.0f}초")
        time.sleep(secs + 2)  # 여유 2초

def setup_driver():
    opts = Options()
    # opts.add_argument("--headless=new")  # 필요시 헤드리스
    opts.add_argument("--window-size=1300,1300")
    # UA 변경 등 필요시 추가
    service = Service(chromedriver_path)
    drv = webdriver.Chrome(service=service, options=opts)
    drv.set_page_load_timeout(60)
    return drv

def click_text(driver, text, template_xpath_key, timeout=10):
    xp = XPATHS[template_xpath_key].format(text=text)
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xp)))
    el.click()
    return el

def try_click(driver, xpath, timeout=10):
    el = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))
    el.click()
    return el

def find_elements(driver, xpath, timeout=10):
    WebDriverWait(driver, timeout).until(EC.presence_of_all_elements_located((By.XPATH, xpath)))
    return driver.find_elements(By.XPATH, xpath)

def select_date(driver, dt, max_month_jumps=12):
    yyyy = f"{dt.year:04d}"
    mm   = f"{dt.month:02d}"
    dd   = f"{dt.day:02d}"
    day  = f"{dt.day}"

    # 1) data-date로 바로 클릭
    for _ in range(2):
        try:
            xp = XPATHS["date_cell_data_date"].format(yyyy=yyyy, mm=mm, dd=dd)
            try_click(driver, xp, timeout=2)
            return True
        except Exception:
            # 2) 일자 텍스트로 클릭 (현재 표시 월이어야 함)
            try:
                xp_text = XPATHS["date_cell_text"].format(day=day)
                try_click(driver, xp_text, timeout=2)
                return True
            except Exception:
                # 3) 다음 달로 넘기며 재시도
                try:
                    try_click(driver, XPATHS["cal_next"], timeout=2)
                except Exception:
                    pass
    # 월 넘김을 좀 더 시도
    for _ in range(max_month_jumps):
        try:
            xp = XPATHS["date_cell_data_date"].format(yyyy=yyyy, mm=mm, dd=dd)
            try_click(driver, xp, timeout=2)
            return True
        except Exception:
            try:
                try_click(driver, XPATHS["cal_next"], timeout=2)
            except Exception:
                # prev로도 시도
                try:
                    try_click(driver, XPATHS["cal_prev"], timeout=2)
                except Exception:
                    time.sleep(0.3)
    return False

def select_first_available_time(driver):
    try:
        btns = find_elements(driver, XPATHS["time_buttons"], timeout=5)
        for b in btns:
            try:
                if b.is_enabled():
                    b.click()
                    return True
            except StaleElementReferenceException:
                continue
    except TimeoutException:
        return False
    return False

def login_if_needed(driver):
    if LOGIN_URL:
        driver.get(LOGIN_URL)
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, XPATHS["login_id"])))
            driver.find_element(By.XPATH, XPATHS["login_id"]).send_keys(USER_ID)
            driver.find_element(By.XPATH, XPATHS["login_pw"]).send_keys(USER_PW)
            try_click(driver, XPATHS["login_btn"])
            # 로그인 후 리다이렉트 대기
            time.sleep(2)
        except Exception:
            pass

def finalize(driver):
    try:
        # 다음 → 동의 → 완료(사이트 구조에 맞게 단계 조정)
        try:
            try_click(driver, XPATHS["next_btn"], timeout=3)
        except Exception:
            pass
        try:
            try_click(driver, XPATHS["agree_checkbox"], timeout=3)
        except Exception:
            pass
        try:
            try_click(driver, XPATHS["confirm_btn"], timeout=5)
        except Exception:
            pass
        return True
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────────────
# 메인 로직
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if RUN_AT_MIDNIGHT:
        wait_until_kst_midnight()

    driver = setup_driver()
    try:
        login_if_needed(driver)
        driver.get(SITE_URL)

        target_dates = get_target_weekend_dates()
        print("[INFO] 대상 날짜(주말):", target_dates)

        reserved = False

        for loc in LOCATIONS:
            if reserved: break
            # 위치 선택
            try:
                click_text(driver, loc, "location_text", timeout=5)
                print(f"[INFO] 위치 선택: {loc}")
            except Exception as e:
                print(f"[WARN] 위치 선택 실패: {loc}, {e}")
                continue

            # 코스(18홀) 선택
            course_ok = True
            for key in COURSE_KEYWORDS:
                try:
                    click_text(driver, key, "course_text", timeout=3)
                    print(f"[INFO] 코스 선택: {key}")
                except Exception as e:
                    print(f"[WARN] 코스 선택 실패: {key}, {e}")
                    course_ok = False
                    break
            if not course_ok:
                continue

            # 날짜 루프
            for dt in target_dates:
                try:
                    ok = select_date(driver, dt)
                    if not ok:
                        print(f"[WARN] 날짜 선택 실패: {dt}")
                        continue

                    # 시간 선택(가장 이른 '예약/가능' 버튼)
                    if select_first_available_time(driver):
                        print(f"[INFO] 시간 선택 성공: {dt} @ {loc} (18홀)")
                        # 약관/완료
                        if finalize(driver):
                            print("[INFO] 예약 완료 시도")
                        else:
                            print("[INFO] 예약 완료 단계 실패(확인 필요)")
                        reserved = True
                        break
                    else:
                        print(f"[INFO] 선택 가능 시간 없음: {dt} @ {loc}")
                except Exception as e:
                    print(f"[ERR] 처리 중 예외: {dt} @ {loc} -> {e}")
                    continue

        if not reserved:
            print("[INFO] 조건에 맞는 예약을 찾지 못했습니다. 셀렉터 점검 필요.")

        # 디버깅용 대기
        time.sleep(3)

    finally:
        # 필요 시 주석 해제
        # driver.quit()
        pass
