library(data.table)
library(zoo)
library(lubridate)
library(ggplot2)
library(forecast)
library(tseries)
setwd("C:/Users/user/Desktop/hykim/시계열분석/data")
nile <- fread("Lec6_Nile.csv")
str(nile)
nile_ts <- ts(nile$val, start=min(nile$year), frequency=1)
plot(nile_ts)

adf <- adf.test(nile_ts)
print(adf) #p=0.064, 귀무가설 기각x -> 비정상

fit <- auto.arima(nile_ts)
summary(fit)

checkresiduals(fit)

nile_forecast <- forecast(fit, h=10)
plot(nile_forecast) 
