library(data.table)
library(zoo)
library(lubridate)

# 업샘플링
setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
emails<-fread("Lec3_emails.csv")
emails[,week:=as.Date(week)] # week열을 Date타입으로 변환

# 주 단위 별로 이메일 열람 횟수 집계
week_emails <- emails[, .(count_emails=.N),by = week] 
all_dates <- seq(from = min(week_emails$week), 
                 to = max(week_emails$week),
                 by = "day") # 전체 날짜 시퀀스 생성

setkey(week_emails, week) # week_emails테이블에 대해 키를 week로 설정
upsampled <- week_emails[.(all_dates)] 
# all_dates벡터를 조인 키로 사용해 weeks_emails를 조회하여 원래 없던 날짜가 NA로 표시

upsampled[is.na(count_emails), count_emails := 0] # NA를 0으로 대체
upsampled[, block := floor((.I-1)/7)+1] 
# data.table에서 현재 행 번호(1부터 시작)를 기준으로 7일씩 묶기

# 업샘플링하기 
upsampled[, count_emails := { 
  total <- sum(count_emails) # 해당 블록(7일) 합
  avg <- total /.N         # .N: 현재 그룹(블록) 내 행 개수
  val <- ceiling(avg)       # 올림 처리
  rep(val,.N)              # 블록 내 각 행(일자)에 동일한 값 할당
}, by=block]

# 예제1
# 4
Sys.setlocale("LC_TIME", "C") # 영문 로케일 설정
upsampled[, day:=weekdays(week)] # 요일 변수 생성
upsampled[week==as.Date("2015-02-09"), day]

# 5
ratio_map <- c(
  "Monday" = 0.3,
  "Tuesday" = 0.15,
  "Wednesday" = 0.15,
  "Thursday" = 0.15,
  "Friday" = 0.25,
  "Saturday" = 0.00,
  "Sunday" = 0.00
) # 비율 설정
upsampled[,ratio:=ratio_map[day]] # 비율 매핑 

# 6
upsampled[, count_emails := {
  block_sum <- sum(count_emails, na.rm=T) # 블록별 전체 합계 계산
  new_vals <- ratio * block_sum           # 각 요일의 비율 곱하기
  new_vals <- ceiling(new_vals)           # 올림 처리
}, by = block]
upsampled[week==as.Date("2015-02-14"), count_emails]
upsampled[week==as.Date("2018-05-16"), count_emails]
upsampled[week==as.Date("2015-04-28"), count_emails]
upsampled[week==as.Date("2017-01-02"), count_emails]

# 다운 샘플링
# 데이터 불러오기 
unemp<-fread("Lec2_UNRATE.csv")
unemp[, DATE:=as.Date(DATE)]

# 다운 샘플링을 적용하여 1월에 측정된 것만 출력(서브 샘플링)
unemp[seq.int(from=1, to=nrow(unemp), by=12)]

unemp[,mean(UNRATE), by=format(DATE,"%Y")] #연도별 실업률 평균("%Y-%m")
unemp[, .(avg_unrate=mean(UNRATE)), by=.(month=format(DATE,"%m"))] #월별 실업률 평균 

# 예제
# 4
donations <- fread("Lec3_donations.csv")
head(donations)

# 5
donations[, month := floor_date(timestamp, "month")]
# 해당 타임 스탬프를 해당 달의 1일 00:00:00로 내림
donations[order(month)]

# 6
monthly_donations <- donations[,.(monthly_sum=sum(amount)), by=month]
tail(monthly_donations[order(monthly_sum)])
# amount: 기부금액

# 7
monthly_don_avg <- donations[,.(monthly_avg=mean(amount)),by=month]
monthly_don_avg[order(monthly_avg)]

# 8
donations[,week:=floor_date(timestamp, "week")]
weekly_donations <- donations[,.(weekly_sum=sum(amount)), by=week]
weekly_donations[order(weekly_sum)]

# 9 
donations[,week_mon:=floor_date(timestamp, "week", week_start=1)]
weekly_donation_mon <- donations[,.(weekly_sum_mon=sum(amount)), by=week_mon]
weekly_donation_mon[order(weekly_sum_mon)]

# 분기별 평균 실업률 계산(Q1, Q2, Q3, Q4)
unemp <- fread("Lec2_UNRATE.csv")
unemp[, DATE:=as.Date(DATE)]
unemp[, quarter := paste0(format(DATE,"%Y"),"-Q",
                          ceiling(as.integer(format(DATE,"%m"))/3))]
quarterly <- unemp[,.(avg_unrate=mean(UNRATE)), by=quarter]

bad <- unemp[UNRATE>7]
nrow(bad)
mean(bad$UNRATE)

ts_unemp <- ts(unemp$UNRATE, start=c(1948,1), frequency=12)
fit <- stl(ts_unemp, s.window="periodic")
window()
plot(fit)
