import sys
import os
from gtts import gTTS
import pygame
import time

# 소리 출력을 위한 초기화
pygame.mixer.init()

def speak(text):
    try:
        tts = gTTS(text=text, lang='ko')
        tts.save("voice.mp3")
        pygame.mixer.music.load("voice.mp3")
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            continue
        pygame.mixer.music.unload()
        os.remove("voice.mp3")
    except Exception as e:
        print(f"\n[음성 출력 오류]: {e}")

# 조사를 자동으로 선택해주는 함수 (이/가)
def get_josa(word):
    if not word: return ""
    # 마지막 글자의 유니코드 값을 확인하여 받침 유무 판별
    last_char = word[-1]
    if (ord(last_char) - 0xAC00) % 28 > 0:
        return "이"
    else:
        return "가"

target_objects = {
    'elevator' : '엘리베이터',
    'board' : '보드판',
    'vending_machine' : '자판기',
    'trash_bin' : '쓰레기통',
    'self_service_cafe' : '무인 카페',
    'water_dispenser' : '정수기',
    'locker' : '사물함',
    'door' : '문',
    'obstacle' : '장애물',
    'ATM' : 'ATM기',
    'snack_vending_machine' : '과자 자판기',
    'photo_copier' : '복사기',
    'person' : '사람',
    'lectern' : '교탁',
    'desk': '책상',
    'chair': '의자',
    'signboard': '표지판'
}

last_speak_time = 0

print("보행 보조 '목록 안내' 시스템이 시작되었습니다...")

for line in sys.stdin:
    sys.stdout.write(line)
    sys.stdout.flush()
    
    # YOLO 로그 분석 (감지된 숫자가 있는지 확인)
    if any(f"{i} " in line for i in range(1, 10)):
        current_time = time.time()
        
        if current_time - last_speak_time > 5:
            detected_now = []
            
            for eng_name, kor_name in target_objects.items():
                if eng_name in line:
                    detected_now.append(kor_name)
            
            if detected_now:
                detected_now = list(set(detected_now))
                
                # 물체 목록 합치기
                object_list_str = ", ".join(detected_now)
                
                # 마지막 물체에 맞는 조사 선택 (예: "책상" -> "책상이", "의자" -> "의자가")
                josa = get_josa(detected_now[-1])
                message = f"앞에 {object_list_str}{josa} 있습니다."
                
                print(f"\n[음성 안내 중]: {message}")
                speak(message)
                last_speak_time = current_time
