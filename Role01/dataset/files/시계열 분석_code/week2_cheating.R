library(zoo)
library(data.table)

# 시계열 데이터 다루기(ts(), as.POSIXct())
data <- rnorm(100) 
head(data)
ts_data<-ts(data, frequency=12, start = c(2020, 1)) # 시계열 객체로 변환
head(ts_data)
plot(ts_data)
datetime<-as.POSIXct("2025-02-27 14:50:28",
                     format="%Y-%m-%d %H:%M:%S",
                     tz="UTC") # 텍스트(문자형) 형태의 날짜를 POSIXct객체의 형태로 변환
OlsonNames() #tz 인수는 원하는 인수 지정 (이 함수 참조)

# 시계열 데이터 탐색기법(decompose())
data("AirPassengers")
str(AirPassengers)
plot(AirPassengers)
AirPassengers_d<-decompose(AirPassengers) # 시계열 데이터를 추세, 계절성, 잔차로 분해
plot(AirPassengers_d)

# 패키지소개-zoo(zoo(), merge(), lag())
data1<-rnorm(10)
dates<-as.Date("2026-03-10")+0:9
data_z<-zoo(data1, order.by = dates) # 시계열 객체 생성
# data1: 시계열 데이터
# order.by: 데이터에 대응하는 인덱스(데이터의 길이와 일치해야함)
plot(data_z)
dates1<-as.Date("2026-03-13")+0:9
z1<-zoo(rnorm(10), order.by = dates)
z2<-zoo(rnorm(10), order.by = dates1)
merge(z1, z2) # z1, z2 병합, 해당 날짜에 값이 없으면 NA값으로 채움(결측치 처리)

lag_z1<-lag(z1, k=2) # k: 지연 시점 수
# 과거 데이터가 현재에 미치는 영향 분석
# 며칠 전에 데이터가 가장 큰 영향을 미치는가?

# 패키지 소개-data.table(data.table(), setkey(), roll=())
# 예시 데이터 생성
dt1<-data.table(time=as.POSIXct(c("2025-01-01 00:00:00",
                                    "2025-01-01 01:00:00",
                                    "2025-01-01 02:00:00",
                                    "2025-01-01 03:00:00")),
                temperature=c(10,12,11,13))
dt2<-data.table(time=as.POSIXct(c("2025-01-01 00:30:00",
                                  "2025-01-01 01:45:00",
                                  "2025-01-01 02:15:00")),
                humidity=c(70, 65, 68))
setkey(dt1, time) # 'time'컬럼을 키 설정, 데이터 검색과 조인(join) 속도 향상
setkey(dt2, time)
result<-dt1[dt2, roll=T] # dt2의 각 시각에 대해 dt1의 가장 가까운 값을 찾음
print(result) 
# roll = TRUE: 롤링 허용, roll = 0: 정확히 일치하는 값만 허용(불일치 시 NA)

# 예제10
z_temp <- zoo(result$temperature, order.by=result$time)
z_hum <- zoo(result$humidity, order.by=result$time)

# 누락된 데이터 다루기
time<-1:10
value<-c(10, 12, NA, NA, 18, 20, NA, 25, 27, 30)
data<-data.frame(time, value)

# linear interpolation
linear<-approx(data$time, data$value, xout=data$time)

# spline interpolation
spli<-spline(data$time, data$value, xout=data$time)

setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")

# Lec2_UNRATE.csv로 누락된 데이터 다루기 
unemp<-fread("Lec2_UNRATE.csv")
head(unemp)
unemp[, DATE:=as.Date(DATE)] # unemp에 DATE로 채워진 새로운 열 추가
setkey(unemp, DATE)
missing_sample<-scan("Lec2_sample.txt", what=integer()) # 정수(integer)형태의 벡터로 저장
unemp_missing<-unemp[-missing_sample]
missing_sample_high<-scan("Lec2_sample_high.txt", what=integer())
unemp_missing_high <- unemp[-missing_sample_high]

all_dates<-seq(from=unemp$DATE[1], to=tail(unemp$DATE, 1), by="months")

unemp_missing<-unemp_missing[J(all_dates), roll=0]
unemp_missing_high<-unemp_missing_high[J(all_dates), roll=0]
# all_dates를 키로 하는 조인을 수행하는데 정확히 일치하는 날짜만 매칭, 없으면 NA

unemp_missing[,rpt:=is.na(UNRATE)] # UNRATE가 결측치인지 여부를 나타내는 새 열(rpt) 추가
unemp_missing_high[,rpt:=is.na(UNRATE)]

# Forward Fill:누락된 값이 나타나기 직전의 값으로 누락된 값을채우는 가장 간단한 방법.
unemp_missing[,impute_ff:=na.locf(UNRATE, na.rm=F)]
unemp_missing_high[,impute_ff:=na.locf(UNRATE, na.rm=F)]
# na.locf(data, na.rm=F): 결측치를 이전 관측값으로 대치

unemp[300:400, plot(DATE,UNRATE,col=1, type='b')]
unemp_missing[300:400, lines(DATE, impute_ff, col=2)]
unemp_missing[300:400][rpt==T, points(DATE, impute_ff, col=2, pch=24)]

unemp[300:400, plot(DATE,UNRATE,col=1, type='b')]
unemp_missing_high[300:400, lines(DATE, impute_ff, col=3)]
unemp_missing_high[300:400][rpt==T, points(DATE, impute_ff, col=3, pch=19)]
