
from description_generator import generate_description

# 테스트용 파일
filename = "student_score_analysis.py"

extracted_text = """
import pandas as pd

df = pd.read_csv("student_scores.csv")

print(df.head())
print(df.describe())

average = df["score"].mean()
print("평균 점수:", average)
"""

# Ollama로 description 생성
description = generate_description(filename, extracted_text)

print("\n생성된 description:")
print(description)
