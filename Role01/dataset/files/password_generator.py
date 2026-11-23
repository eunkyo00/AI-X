import string
import secrets

# 비밀번호 생성 함수
def generate_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#$%"
    password = ""

    for i in range(length):
        password += secrets.choice(characters)

    return password

# 비밀번호 5개 생성
for i in range(5):
    print(f"비밀번호 {i+1}: {generate_password()}")