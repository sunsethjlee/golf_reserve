from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time

# ------------------------------
# 🔧 환경/셀렉터 설정
# ------------------------------
LOGIN_URL = "https://welfare.airforce.mil.kr:446/user/login.do?siteId=welfare&id=welfare_060100000000"
RES_LIST_URL = "https://welfare.airforce.mil.kr:446/cli/wefResList.do?siteId=welfare&id=welfare_030101000000"

USER_ID = "billy0327"
USER_PW = "golf0327!"
APPLICANT_NAME = "이혜진"
PHONE_TO_SEARCH = "010- 9362- 67"  # 실제 검색어로 맞춰줘

# 예약 테이블/폼 셀렉터 (사이트에 맞게 필요 시 조정)
X_RES_TABLE_THEAD = '//*[@id="reservation"]//table/thead/tr'
X_RES_HEADER_ALL  = '//*[@id="reservation"]/div[2]/table/thead/tr/th'

# 슬롯(수원/성남) 행 번호
ROW_SUWON    = 6
ROW_SEONGNAM = 8

# 예약신청 폼 요소들
X_DROPDOWN_TIME = '//*[@id="reservation"]/form[2]/div[1]/table/tbody/tr[2]/td/select'
X_INPUT_NAME    = '//*[@id="nameKr1"]'
X_ADDRBOOK_LINK = '//*[@id="reservation"]/form[2]/div[3]/fieldset/table/tbody/tr[1]/td[2]/span/a'

# 주소록 팝업 내 (사이트 DOM에 맞게 필요 시 수정)
X_POPUP_SEARCH_INPUT  = '//*[@id="searchWord"]'               # 예시
X_POPUP_SEARCH_BUTTON = '//*[@id="btnSearch"]'                # 예시(없으면 Enter로 대체)
X_POPUP_FIRST_RESULT  = '(//table[@id="resultTbl"]//tr/td/a)[1]'  # 예시: 첫 번째 결과 클릭

# ------------------------------
# 공용 유틸
# ------------------------------
def wait_dom_ready(driver, timeout_sec=20):
    """document.readyState == complete 대기"""
    end = time.time() + timeout_sec
    while time.time() < end:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return
        except Exception:
            pass
        time.sleep(0.2)
    # 넘어감 (일부 페이지는 complete 전에 인터랙션 가능)

def ensure_reservation_table_context(driver, wait):
    """현재 문서 또는 iframe에서 예약 thead 보일 때까지 전환"""
    # 현재 문서 시도
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, X_RES_TABLE_THEAD)))
        return
    except TimeoutException:
        pass

    # iframe 순회
    frames = driver.find_elements(By.TAG_NAME, 'iframe')
    for idx in range(len(frames)):
        driver.switch_to.default_content()
        driver.switch_to.frame(idx)
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, X_RES_TABLE_THEAD)))
            return
        except TimeoutException:
            continue

    driver.switch_to.default_content()
    raise TimeoutException("예약 테이블 thead를 찾지 못했습니다. (컨텍스트/셀렉터 점검 필요)")

def collect_weekend_cols(driver):
    """thead의 th를 읽어 '토'/'일' 들어간 열 인덱스를 반환"""
    headers = driver.find_elements(By.XPATH, X_RES_HEADER_ALL)
    start_col = 2 if len(headers) >= 2 else 1
    end_col = len(headers)
    target_cols = []
    for i in range(start_col, end_col + 1):
        th_xpath = f'//*[@id="reservation"]/div[2]/table/thead/tr/th[{i}]'
        try:
            txt = driver.find_element(By.XPATH, th_xpath).text.strip()
            if ('토' in txt) or ('일' in txt):
                target_cols.append(i)
        except NoSuchElementException:
            pass
    return target_cols

def is_completed_cell(driver, row, col) -> bool:
    """해당 셀이 '신청완료' 상태인지 미리 검사"""
    td_xpath = f'//*[@id="reservation"]/div[2]/table/tbody/tr[{row}]/td[{col}]'
    try:
        text = driver.find_element(By.XPATH, td_xpath).text.strip()
        if '신청완료' in text:
            return True
        # 클래스 마크업 기반 (있으면)
        driver.find_element(By.XPATH, td_xpath + '//*[contains(@class,"app-text") and contains(.,"신청완료")]')
        return True
    except NoSuchElementException:
        return False

def open_slot(driver, wait, row, col) -> bool:
    """
    (row,col) 셀을 클릭해 상세(예약신청 폼) 진입 시도.
    - '신청완료'면 스킵
    - 클릭 후 새 창/URL 변경/폼 표식 중 하나라도 보이면 성공
    - 아무 변화 없으면 실패로 간주
    """
    if is_completed_cell(driver, row, col):
        print(f"[스킵] ({row},{col}) 신청완료")
        return False

    candidates = [
        f'//*[@id="reservation"]/div[2]/table/tbody/tr[{row}]/td[{col}]/a/span',
        f'//*[@id="reservation"]/div[2]/table/tbody/tr[{row}]/td[{col}]//a',
        f'//*[@id="reservation"]/div[2]/table/tbody/tr[{row}]/td[{col}]//span'
    ]

    before_url = driver.current_url
    before_handles = set(driver.window_handles)

    clicked = False
    for xp in candidates:
        try:
            elem = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
            elem.click()
            clicked = True
            break
        except Exception:
            continue

    if not clicked:
        print(f"[실패] ({row},{col}) 클릭 가능한 요소 없음")
        return False

    def navigated_or_form_loaded(drv):
        if len(drv.window_handles) > len(before_handles):
            return True
        if drv.current_url != before_url:
            return True
        try:
            if drv.find_elements(By.XPATH, "//*[contains(text(),'예약신청') or contains(text(),'운동 희망시간')]"):
                return True
            if drv.find_elements(By.XPATH, "//select[option[normalize-space(.)='모든시간']]"):
                return True
        except Exception:
            pass
        return False

    t0 = time.time()
    while time.time() - t0 < 6:  # 최대 6초 대기
        if navigated_or_form_loaded(driver):
            return True
        time.sleep(0.2)

    print(f"[실패] ({row},{col}) 클릭했으나 이동/폼 감지 실패 → 다음 셀로")
    return False

def switch_to_latest_window(driver, timeout=8):
    """가장 최근 창/탭으로 전환 (이미 떠 있으면 마지막 핸들로)"""
    end = time.time() + timeout
    last = driver.window_handles[-1]
    driver.switch_to.window(last)
    while time.time() < end:
        try:
            # 정상 접근 가능하면 종료
            driver.title  # 접근 테스트
            return
        except Exception:
            time.sleep(0.1)

def switch_into_form_iframe_if_any(driver):
    """예약신청 폼이 iframe 안이면 진입 (못 찾으면 원복)"""
    def has_form_marker():
        try:
            if driver.find_elements(By.XPATH, "//*[contains(text(),'예약신청') or contains(text(),'운동 희망시간')]"):
                return True
            if driver.find_elements(By.XPATH, "//select[option[normalize-space(.)='모든시간']]"):
                return True
        except Exception:
            pass
        return False

    if has_form_marker():
        return

    frames = driver.find_elements(By.TAG_NAME, 'iframe')
    for idx in range(len(frames)):
        driver.switch_to.default_content()
        driver.switch_to.frame(idx)
        if has_form_marker():
            return
    driver.switch_to.default_content()

def find_time_select(driver, wait, timeout=10):
    """'모든시간' 옵션이 있는 select를 다각도로 탐색하여 Select 반환"""
    candidates = [
        X_DROPDOWN_TIME,
        "//select[option[normalize-space(.)='모든시간']]",
        "//label[contains(.,'운동 희망시간')]/following::select[1]",
        "//select[@name='hopeTime' or @id='hopeTime']",
    ]
    last_err = None
    for xp in candidates:
        try:
            elem = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp))
            )
            return Select(elem)
        except Exception as e:
            last_err = e
    raise TimeoutException(f"시간 선택 select를 찾지 못함. 마지막 오류={type(last_err).__name__}")

def handle_reservation_form(driver, wait):
    """예약신청 폼: 시간=모든시간, 이름 입력, 주소록 팝업 검색/선택, 60초 대기"""
    # 창/프레임 컨텍스트 정리
    switch_to_latest_window(driver)
    wait_dom_ready(driver)
    switch_into_form_iframe_if_any(driver)

    # 시간: '모든시간'
    sel = find_time_select(driver, wait)
    try:
        sel.select_by_visible_text("모든시간")
    except Exception:
        for v in ("ALL", "all", "A", "모든시간"):
            try:
                sel.select_by_value(v)
                break
            except Exception:
                continue

    # 이름 입력
    name_candidates = [
        X_INPUT_NAME,
        "//input[@name='nameKr1' or @id='nameKr1']",
        "//input[@type='text' and (contains(@placeholder,'이름') or contains(@title,'이름'))]"
    ]
    name_input = None
    for xp in name_candidates:
        try:
            name_input = wait.until(EC.presence_of_element_located((By.XPATH, xp)))
            break
        except TimeoutException:
            continue
    if not name_input:
        raise TimeoutException("이름 입력 필드를 찾지 못했습니다.")
    name_input.clear()
    name_input.send_keys(APPLICANT_NAME)

    # 주소록 링크 클릭 → 팝업에서 검색/선택
    addr_candidates = [
        X_ADDRBOOK_LINK,
        "//a[contains(.,'검색') or contains(.,'주소록') or contains(.,'찾기')]",
    ]
    addr_link = None
    for xp in addr_candidates:
        try:
            addr_link = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
            break
        except TimeoutException:
            continue
    if not addr_link:
        raise TimeoutException("주소록/검색 링크를 찾지 못했습니다.")

    main_handle = driver.current_window_handle
    old_handles = driver.window_handles[:]
    addr_link.click()

    # 팝업 전환
    WebDriverWait(driver, 8).until(lambda d: len(d.window_handles) > len(old_handles))
    popup_handle = next(h for h in driver.window_handles if h not in old_handles)
    driver.switch_to.window(popup_handle)
    wait_dom_ready(driver)

    # 팝업 내 검색/선택
    try:
        search_input = wait.until(EC.presence_of_element_located((By.XPATH, X_POPUP_SEARCH_INPUT)))
        search_input.clear()
        search_input.send_keys(PHONE_TO_SEARCH)
        try:
            driver.find_element(By.XPATH, X_POPUP_SEARCH_BUTTON).click()
        except NoSuchElementException:
            search_input.submit()
        first_result = wait.until(EC.element_to_be_clickable((By.XPATH, X_POPUP_FIRST_RESULT)))
        first_result.click()
    finally:
        # 팝업 닫고 메인 복귀
        try:
            driver.close()
        except Exception:
            pass
        driver.switch_to.window(main_handle)
        switch_into_form_iframe_if_any(driver)

    # 관찰/검토를 위해 잠시 대기
    time.sleep(60)

def back_to_list_and_restore(driver, wait):
    """상세 → 목록 복귀 및 컨텍스트 복원"""
    try:
        driver.back()
    except Exception:
        pass
    wait_dom_ready(driver)
    driver.switch_to.default_content()
    ensure_reservation_table_context(driver, wait)

# ------------------------------
# 실행 시나리오
# ------------------------------
driver = webdriver.Chrome()
wait = WebDriverWait(driver, 15)

# 로그인
driver.get(LOGIN_URL)
wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="encId"]'))).send_keys(USER_ID)
driver.find_element(By.XPATH, '//*[@id="userPw"]').send_keys(USER_PW)
driver.find_element(By.XPATH, '//*[@id="loginForm"]/fieldset/div[3]/a/span').click()
wait.until(EC.alert_is_present()).accept()

# 예약 리스트로 이동 및 컨텍스트 준비
driver.get(RES_LIST_URL)
wait_dom_ready(driver)
ensure_reservation_table_context(driver, wait)

# 주말 컬럼 수집
weekend_cols = collect_weekend_cols(driver)
print("주말 컬럼 인덱스:", weekend_cols)

# 각 주말 열에 대해 수원/성남 순서로 시도
for col in weekend_cols:
    # 수원
    if open_slot(driver, wait, ROW_SUWON, col):
        try:
            handle_reservation_form(driver, wait)
        finally:
            back_to_list_and_restore(driver, wait)
    else:
        print(f"[수원] col={col} 불가(신청완료/클릭불가/미이동)")

    # 성남
    if open_slot(driver, wait, ROW_SEONGNAM, col):
        try:
            handle_reservation_form(driver, wait)
        finally:
            back_to_list_and_restore(driver, wait)
    else:
        print(f"[성남] col={col} 불가(신청완료/클릭불가/미이동)")

# 필요 시 관찰 대기
# time.sleep(9999)
driver.quit()
