library(data.table)
library(zoo)
library(lubridate)
library(ggplot2)
library(forecast)
library(tseries)

setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
air <- fread("Lec4_AirPassengers.csv")
head(air)
setnames(air, c("V1", "V2"), c("Date", "Passengers"))

# 이동평균
# 윈도우 사이즈가 7인 이동평균
air[,ma_7:=rollmean(Passengers, k=7, fill=NA, align="right")]
# k = 7이면 첫 6개의 값은 NA(평균계산x)
# 7번째 데이터부터 이동평균값 생성
# fill: 윈도우가 채워지지 않는 구간에 할당할 값
# align: 해당 시점의 정렬
#"right": 과거 k개 평균(예측 상황에 적합), "center": 앞뒤 포함(분석, 시각화 적합)
# "left": 미래 k개 평균(예측분석에는 부적합)
head(air, 15)

#  k=3, k=7, k=12 이동평균을 각각 구하기 
air[,ma_3:=rollmean(Passengers, k=3, fill=NA, align="right")]
# air[,ma_7:=rollmean(Passengers, k=7, fill=NA, align="right")]
air[,ma_12:=rollmean(Passengers, k=12, fill=NA, align="right")]
air[,Date:=as.Date(paste0(Date, "-01"))]
# paste0로 연월데이터에 '-01'일 추가

# 그래프 그리기 
ggplot(air, aes(x=Date)) + 
  geom_line(aes(y=Passengers, color="Actual"))+
  geom_line(aes(y=ma_3, color="MA3"))+
  geom_line(aes(y=ma_7, color="MA7"))+
  geom_line(aes(y=ma_12, color="MA12"))

# 지수평활(ses)
ts_air <- ts(air$Passenger, frequency=12, start=c(1949, 1))
a_0.1 <- ses(ts_air, h=10, alpha=0.1, initial="simple")
a_0.3 <- ses(ts_air, h=10, alpha=0.3, initial="simple")
a_0.9 <- ses(ts_air, h=10, alpha=0.3, initial="simple")
a_opt <- ses(ts_air, h=10, alpha=NULL, initial="simple")
# ses(data, h=예측하고자 하는 미래 시점 개수, alpha=평활계수, initial=초기값 설정) 
# alpha=NULL이면 최적의 계수 추정
# initial= "optimal":초차 최소화 기준으로 추정, "simple":첫 관측값을 초기값으로

# 정확도 비교
accuracy(a_0.1)
accuracy(a_0.3)
accuracy(a_0.9)
accuracy(a_opt)
# RMSE값 비교
# a=0.1, 52.284
# a=0.3, 45.703
# a=0.9, 45.720
# a=opt, 33.594

# MASE=1.04~1.05
# Naive보다 낮은 성능
# 원인: a값 설정, 초기값 사용 방식 등

# 데이터 프레임으로 만듦 
df<-data.frame(Time=as.numeric(time(ts_air)),
               Actual=as.numeric(ts_air),
               a_0.1=as.numeric(a_0.1$fitted),
               a_0.3=as.numeric(a_0.3$fitted),
               a_0.9=as.numeric(a_0.9$fitted),
               a_opt=as.numeric(a_opt$fitted))
# 그래프 그리기 
ggplot(df, aes(x=Time)) + geom_line(aes(y=Actual, color="Actual"))+
  geom_line(aes(y=a_0.1, color="a=0.1"))+
  geom_line(aes(y=a_0.3, color="a=0.3"))+
  geom_line(aes(y=a_0.9, color="a=0.9"))+
  geom_line(aes(y=a_opt, color="a=opt"))

# 예제1
# 5
unemp<-fread("Lec2_UNRATE.csv")
head(unemp)
unemp[,ma_13:=rollmean(UNRATE, k=13, fill=NA, align = "right")]
unemp[DATE=="1949-08-01", ma_13]

# 6
ts_unemp <- ts(unemp$UNRATE, frequency = 12, start=c(1948, 1))
a_0.4 <- ses(ts_unemp, h=7, alpha=0.4, initial="simple")
a_0.4$fitted
a_0.4$mean

# 7
max(window(a_0.4$fitted, start=c(1948, 1), end=c(1948, 12)))
which.max(window(a_0.4$fitted, start=c(1948, 1),end=c(1948, 12)))

# 8
opt <- ses(ts_unemp, h=7, alpha=NULL, initial="simple")
opt$mean

# 9
max(window(opt$fitted, start=c(1948, 1), end=c(2017,10)))

# 10
accuracy(a_0.4)
accuracy(opt)
a_0.4$model
opt$model

# ADF검정
adf.test(ts_air)            # 1.adf 실행(비정상)
adf.test(log(ts_air))       # 2.log 변환
adf.test(diff(ts_air))      # 3.차분 
adf.test(diff(log(ts_air))) # 4. 로그 변환 후 차분

# 예제2
# 1
unrate <- fread("Lec2_UNRATE.csv")
setnames(unrate, c("DATE", "UNRATE"), c("Date", "Rate"))
head(unrate)

# 2
ts_rate <- ts(unrate$Rate, frequency = 12, start=c(1948, 1))
window(ts_rate, start=c(1957, 1), end=c(1957, 12))

# 3
unrate[,ma_3:=rollmean(Rate, k=3, fill=NA, align="right")]
unrate[,ma_6:=rollmean(Rate, k=6, fill=NA, align="right")]
unrate[,ma_12:=rollmean(Rate, k=12, fill=NA, align="right")]

# 4
ses_02 <- ses(ts_rate, h=12, alpha=0.2, initial="simple")
accuracy(ses_02)

ses_05 <-ses(ts_rate, h=12, alpha=0.5, initial="simple")
accuracy(ses_05)

ses_08 <- ses(ts_rate, h=12, alpha=0.8, initial="simple")
accuracy(ses_08)
