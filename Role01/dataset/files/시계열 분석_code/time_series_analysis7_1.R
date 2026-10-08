library(data.table)
library(zoo)
library(lubridate)
library(forecast)
setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
temps<-fread("Lec7_global_temps.csv")
head(temps)
temps[,Date:=as.Date(Date, format="%Y-%m-%d")]
temps_daily<-temps[,.(Mean_daily=mean(Mean)), by=.(Date)]
start_year <- as.numeric(format(min(temps_daily$Date),"%Y"))
setorder(temps_daily, Date)
temps_ts <- ts(temps_daily$Mean_daily, start=c(as.numeric(format(min(temps_daily$Date), "%Y")),1),
               frequency=12)
par(mar=c(1, 1, 1, 1))
plot(temps_ts)

air <- fread("Lec4_AirPassengers.csv")
head(air)
setnames(air, c("V1","V2"), c("Date", "Passengers"))
ts_air <- ts(air$Passengers, frequency=12, start=c(1949,1))
fit_sarima <- auto.arima(ts_air)
summary(fit_sarima)
checkresiduals(fit_sarima)
