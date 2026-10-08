library(data.table)
library(zoo)
library(lubridate)
library(ggplot2)
library(forecast)
library(tseries)
setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
temps <- fread("Lec7_global_temps.csv")
head(temps)
temps[,Date:=as.Date(Date, format="%Y-%m-%d")]
temps_daily <- temps[,.(Mean_daily=mean(Mean)),by=.(Date)]
setorder(temps_daily, Date)

# 과제
# 5
temps_ts <- ts(temps_daily$Mean_daily, 
               start=c(as.numeric(format(min(temps_daily$Date),"%Y")),1),
               frequency=12)
plot(temps_ts)

# 6
fit <- auto.arima(temps_ts)
summary(fit)

# 7
checkresiduals(fit)

forec <- forecast(fit, h=12)

air <- fread("Lec4_AirPassengers.csv")
setnames(air, c("V1","V2"), c("Date", "Passengers"))
ts_air <- ts(air$Passengers, frequency=12, start=c(1949,1))
fit_arima <- auto.arima(ts_air, seasonal=F)
summary(fit_arima)
checkresiduals(fit_arima)

fit_sarima <- auto.arima(ts_air)
summary(fit_sarima)
checkresiduals(fit_sarima)
