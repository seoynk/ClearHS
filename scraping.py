import requests
import json
import time
import datetime
from bs4 import BeautifulSoup
import pandas as pd

# 1. 공통 헤더 및 쿠키 설정
headers = {
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Origin': 'https://unipass.customs.go.kr',
    'Pragma': 'no-cache',
    'Referer': 'https://unipass.customs.go.kr/clip/index.do',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36',
    'X-Requested-With': 'XMLHttpRequest',
    'isAjax': 'true'
}

cookies = {
    'WMONID': 'GxIgEoCnv_F',
    'JSESSIONID': '00020KGkqVxFuL8yOmI5HATpUECIjd8K6bDuu7V5g5afuM36zwHv2bEyViWREJ2EwbunWH_4kebM8jjjhdULZfwVt0ewPbhpHgkhPiRLW4gemCv_ZxLtQZPtDBe_BizuyrBi:eul31:csp31'
}

# --- [STEP 1] 목록 스크래핑 (자동 종료 무한 루프 버전) ---
LIST_URL = 'https://unipass.customs.go.kr/clip/prlstclsfsrch/retrieveDmstPrlstClsfCaseLst2.do'
payload = {
    'pageIndex': '1', 'pageUnit': '10', 'orderColumns': 'ENFR_DT desc', 'prlstClsfCaseTpcd': '01',
    'rrdcNo': '0072026001996', 'srchYn': 'Y', 'scrnTp': 'WDTH', 'sortColm': '', 'sortOrdr': '',
    'atntSrchTp': '', 'docId': '', 'scrnId': '', 'reffNo': '', 'dtrmHsSgn': '',
    'stDt': '2025-12-01', 'edDt': '2026-06-30', 'cmdtNm': '', 'cmdtDesc': '', 'dtrmRsnCn': '',
    'srwr': '', 'pagePerRecord': '10', 'initPageIndex': '1',
    'ULS0203037S_F1_savedToken': 'HB6F1JPXOHBDI80NBWOTG2AB2NTZ6LAY', 'savedToken': 'ULS0203037S_F1_savedToken',
    'txtEnfrDt': '20260508', 'txtDtrmHsSgn': '2309.90-2099', 'attchFileId': 'PCA-20260507-000064043810gWU1'
}

all_items = []
current_page = 1 # 1페이지부터 시작

print("1단계: 자동 종료 목록 스크래핑을 시작합니다...")
list_headers = headers.copy()
list_headers['Accept'] = 'application/json, text/javascript, */*; q=0.01'

while True:  # 데이터가 끝날 때까지 무한 반복
    payload['pageIndex'] = str(current_page)
    try:
        response = requests.post(LIST_URL, headers=list_headers, cookies=cookies, data=payload)
        response.raise_for_status()
        json_data = response.json()
        
        if 'uls_dmst' in json_data and 'itemList' in json_data['uls_dmst']:
            page_items = json_data['uls_dmst']['itemList']
            
            # [핵심 조건] 이번 페이지에 데이터가 한 건도 없다면? -> 수집 끝 Loop 탈출!
            if not page_items or len(page_items) == 0:
                print(f"🏁 {current_page}페이지에 더 이상 데이터가 없습니다. 목록 수집을 종료합니다.")
                break
                
            all_items.extend(page_items)
            print(f" 목록 {current_page} 페이지 수집 완료 (누적 {len(all_items)}건)")
            
            current_page += 1 # 다음 페이지로 넘어가기
        else:
            print(" 예상치 못한 데이터 구조이거나 세션이 만료되었습니다.")
            break
            
    except Exception as e:
        print(f" {current_page} 페이지 수집 중 에러 발생으로 중단: {e}")
        break
        
    time.sleep(1)

# --- [STEP 2] 상세 페이지 딥트래킹 스크래핑 (물품설명 + 결정사유 원문 추적) ---
DETAIL_URL = 'https://unipass.customs.go.kr/clip/prlstclsfsrch/retrieveDmstPrlstClsfCaseDtl.do'
detail_headers = headers.copy()
detail_headers['Accept'] = 'text/html, */*; q=0.01'

print("\n 2단계: 상세 페이지 원문(물품설명 포함) 수집을 시작합니다...")
total_cnt = len(all_items)

for idx, item in enumerate(all_items):
    rrdc_no = item.get('RRDC_NO')
    if not rrdc_no:
        continue
        
    print(f"[{idx+1}/{total_cnt}] 결정번호 {rrdc_no} 상세 원문 가공 중...")
    
    try:
        detail_payload = {'rrdcNo': rrdc_no}
        detail_res = requests.post(DETAIL_URL, headers=detail_headers, cookies=cookies, data=detail_payload)
        detail_res.raise_for_status()
        
        soup = BeautifulSoup(detail_res.text, 'html.parser')
        
        full_reason = ""
        full_desc = ""
        
        # 1. 결정사유 원문 타겟팅
        reason_target = soup.find(id='dtrmRsnCn') or soup.find('textarea', {'name': 'dtrmRsnCn'})
        if reason_target:
            full_reason = reason_target.get_text(strip=False)
        else:
            for th in soup.find_all('th'):
                if '결정사유' in th.get_text() or '분류이유' in th.get_text():
                    td = th.find_next_sibling('td')
                    if td:
                        full_reason = td.get_text(strip=False)
                        break

        # 2.  한국어 물품설명 원문 타겟팅 (gdsDesc 영역 저격)
        # 관세청 상세 팝업에서는 gdsDesc 라는 ID나 이름을 가진 textarea/셀에 한국어 상세 규격이 들어옵니다.
        desc_target = soup.find(id='gdsDesc') or soup.find('textarea', {'name': 'gdsDesc'}) or soup.find(id='cmdtDesc')
        if desc_target:
            full_desc = desc_target.get_text(strip=False)
        else:
            # ID 매칭 실패 시 테이블 th 구조로 2차 추적
            for th in soup.find_all('th'):
                th_text = th.get_text()
                if '물품설명' in th_text or '물품상태' in th_text or '상세설명' in th_text:
                    td = th.find_next_sibling('td')
                    if td:
                        full_desc = td.get_text(strip=False)
                        break

        # 정제 및 저장 (줄바꿈 기호 유지)
        item['[진짜_물품설명_원문]'] = full_desc.strip() if len(full_desc.strip()) > 5 else item.get('GDS_DESC', '원문 없음')
        item['[진짜_결정사유_원문]'] = full_reason.strip() if len(full_reason.strip()) > 5 else item.get('DTRM_RSN_CN', '원문 없음')
        
    except Exception as e:
        print(f" 상세 수집 에러 ({rrdc_no}): {e}")
        item['[진짜_물품설명_원문]'] = "수집 실패"
        item['[진짜_결정사유_원문]'] = "수집 실패"
        
    time.sleep(1.2)

# --- [STEP 3] 가공 및 엑셀 저장 ---
if all_items:
    df = pd.DataFrame(all_items)
    
    # 1. 원하는 컬럼만 명확하게 정의하고 한글로 이름을 바꿉니다.
    # (왼쪽에 서버 영어 명칭 : 오른쪽에 원하시는 한글 명칭)
    rename_rules = {
        'REFF_NO': '참조번호',
        'ENFR_DT': '시행일자',
        'CSTM_NM': '시행기관',
        'DTRM_HS_SGN': '결정세번',
        'CMDT_NM': '품명',
        '[진짜_물품설명_원문]': '물품설명',
        '[진짜_결정사유_원문]': '결정사유',
        'IMGE_CNT': '이미지건수'
    }
    
    # 2. 존재하는 컬럼들만 추려서 한글 이름으로 치환
    available_cols = [col for col in rename_rules.keys() if col in df.columns]
    df_final = df[available_cols].rename(columns=rename_rules)
    
    # 3. 원하셨던 완벽한 순서대로 컬럼 정렬
    target_order = ['참조번호', '시행일자', '시행기관', '결정세번', '품명', '물품설명', '결정사유', '이미지건수']
    final_order = [col for col in target_order if col in df_final.columns]
    df_final = df_final[final_order]
    
    # 날짜 포맷이 YYYYMMDD로 붙어 나오는 경우 보기 좋게 YYYY-MM-DD로 변환 (선택 사항)
    if '시행일자' in df_final.columns:
        df_final['시행일자'] = df_final['시행일자'].astype(str).apply(
            lambda x: f"{x[:4]}-{x[4:6]}-{x[6:8]}" if len(x) == 8 and x.isdigit() else x
        )

    current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"관세청_창업경진대회_데이터셋_{current_time}.xlsx"
    
    with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
        df_final.to_excel(writer, index=False, sheet_name='품목분류사례')
        
    print(f"\n 맞춤형 데이터셋 제작이 최종 완료되었습니다! 파일명: {file_name}")
    print(" 엑셀을 열고 [텍스트 줄 바꿈]을 지정하시면 한눈에 보실 수 있습니다.")
else:
    print("수집 데이터 없음")