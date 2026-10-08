library(data.table)
library(zoo)
library(lubridate)
library(ggplot2)
library(forecast)
library(tseries)

setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
air <- fread("Lec4_AirPassengers.csv")
head(air)
setnames(air, c("V1","V2"), c("Date", "Passengers"))
air[,ma_7:=rollmean(Passengers, k=7, fill=NA, align="right")]
head(air,15)
air[,ma_3:=rollmean(Passengers, k=3, fill=NA, align="right")]
air[,ma_12:=rollmean(Passengers, k=12, fill=NA, align="right")]
air[,Date := as.Date(paste0(Date, "-01"))]
ggplot(air, aes(x=Date)) + 
  geom_line(aes(y=Passengers, color="Actual"))+
  geom_line(aes(y=ma_3, color="MA3"))+
  geom_line(aes(y=ma_7, color="MA7"))+
  geom_line(aes(y=ma_12, color="MA12"))

ts_air <- ts(air$Passengers, frequency=12, start=c(1949,1))
a_0.1 <-ses(ts_air, h=12, alpha=0.1, initial="simple")
a_0.3 <- ses(ts_air, h=12, alpha=0.3, initial="simple")
a_0.9 <-ses(ts_air, h=12, alpha=0.9, initial="simple")
a_opt <- ses(ts_air, h=12, alpha=NULL, initial="simple")
accuracy(a_0.1)
accuracy(a_0.3)
accuracy(a_0.9)
accuracy(a_opt)
#RMSE 값을 기준으로: 
#a=0.1, 52.284
#a=0.3, 45.720
#a=0.9, 34.736

df <- data.frame(Time=as.numeric(time(ts_air)), 
                 Actual=as.numeric(ts_air),
                 a_0.1=as.numeric(a_0.1$fitted),
                 a_0.3=as.numeric(a_0.3$fitted),
                 a_0.9=as.numeric(a_0.9$fitted),
                 a_opt=as.numeric(a_opt$fitted))
ggplot(df, aes(x=Time)) + geom_line(aes(y=Actual, color="Actual"))+
  geom_line(aes(y=a_0.1, color="a=0.1"))+
  geom_line(aes(y=a_0.3, color="a=0.3"))+
  geom_line(aes(y=a_0.9, color="a=0.9"))+
  geom_line(aes(y=a_opt, color="a=opt"))

unemp <- fread("Lec2_UNRATE.csv")
unemp[,DATE:=as.Date(DATE)]
unemp[,ma_13:=rollmean(UNRATE, k=13, fill=NA, align="right")]

#5
unemp[DATE=="1949-08-01", ma_13]

#6
ts_unemp <- ts(unemp$UNRATE, frequency=12, start=c(1948,1))
a_0.4 <- ses(ts_unemp, h=7, alpha=0.4, initial='simple')
opt <- ses(ts_unemp, h=7, alpha=NULL, initial='simple')
a_0.4$fitted

#6
a_0.4$mean

#7
max(window(a_0.4$fitted, start=c(1948,1), end=c(1948,12)))
which.max(window(a_0.4$fitted, start=c(1948,1), end=c(1948,12)))

#8
opt$mean

#9
max(window(opt$fitted, start=c(1948,1), end=c(2017,10)))

#10
accuracy(a_0.4)
accuracy(opt)
opt$model

adf.test(ts_air)
adf.test(log(ts_air))
adf.test(diff(ts_air))
adf.test(diff(log(ts_air)))


#1
unrate <- fread("Lec2_UNRATE.csv")
head(unrate)
setnames(unrate, c("DATE","UNRATE"), c("Date", "Rate"))
head(unrate)

#2
ts_rate <- ts(unrate$Rate, frequency=12, start=c(1948,1))
window(ts_rate, start=c(1957,1), end=c(1957,12))

#3
unrate[,ma_3 :=rollmean(Rate, k=3, fill=NA, align='right')]
unrate[,ma_6 :=rollmean(Rate, k=6, fill=NA, align='right')]
unrate[,ma_12 :=rollmean(Rate, k=12, fill=NA, align='right')]

#4
ses_02 <- ses(ts_rate, h=12, alpha=0.2, initial="simple")
accuracy(ses_02)

ses_05 <- ses(ts_rate, h=12, alpha=0.5, initial="simple")
accuracy(ses_05)

ses_08 <- ses(ts_rate, h=12, alpha=0.8, initial="simple")
accuracy(ses_08)
