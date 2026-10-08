#install.packages("forecast")
#install.packages("tseries")

library(zoo)
library(data.table)
library(lubridate)
library(ggplot2)
library(forecast)
library(tseries)

setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
air <-fread("Lec4_AirPassengers.csv")
head(air)
setnames(air,c("V1","V2"), c("Date", "Passengers"))
air[,ma_7:=rollmean(Passengers, k=7, fill=NA,align = "right")]
air[,ma_3:=rollmean(Passengers, k=3, fill=NA,align = "right")]
air[,ma_12:=rollmean(Passengers, k=12, fill=NA,align = "right")]
ggplot(air, aes(x = Date)) +
  geom_line(aes(y = Passengers, color = "Actual", group = 1)) +
  geom_line(aes(y = ma_3, color = "MA3", group = 1)) +
  geom_line(aes(y = ma_7, color = "MA7", group = 1)) +
  geom_line(aes(y = ma_12, color = "MA12", group = 1))

ts_air<-ts(air$Passengers, frequency=12, start=c(1949,1))
a_0.3 <- ses(ts_air, h=12, alpha=0.3, initial="simple")
accuracy(a_0.3)

a_0.1 <- ses(ts_air, h=12, alpha=0.1, initial="simple")
a_0.3 <- ses(ts_air, h=12, alpha=0.3, initial="simple")
a_0.9 <- ses(ts_air, h=12, alpha=0.9, initial="simple")
a_opt <- ses(ts_air, h=12, alpha=NULL, initial="simple") #h: ,initial="simple":초기값 그대로 반영
accuracy(a_0.1)
accuracy(a_0.3)
accuracy(a_0.9)
accuracy(a_opt)
#RMSE 값 기준으로:
#a=0.1, 52.284
#a=0.3, 45.720
#a=0.9, 34.736
#변동(알파)값이 클수록 mse가 작아짐(최근값 이용)
#알파가 1에 가까울 수록 최근값을 반영한 것

df<-data.frame(Time=as.numeric(time(ts_air)),
               Actual=as.numeric(ts_air),
               a_0.1=as.numeric(a_0.1$fitted),
               a_0.3=as.numeric(a_0.3$fitted),
               a_0.9=as.numeric(a_0.9$fitted),
               a_opt=as.numeric(a_opt$fitted)) #fitted값이 뭐라고?
ggplot(df,aes(x=Time))+geom_line(aes(y=Actual, color="Actual"))+
  geom_line(aes(y=a_0.1, color="a=0.1"))+
  geom_line(aes(y=a_0.3, color="a=0.3"))+
  geom_line(aes(y=a_0.9, color="a=0.9"))+
  geom_line(aes(y=a_opt, color="a=opt"))
#alpha가 클수록 과적합이 생길 수 있음

unemp<-fread("Lec2_UNRATE.csv")
unemp[,DATE:=as.Date(DATE)]
unrate[,ma_13:=rollmean(UNRATE, k=13, fill=NA,align = "right")]

#5
unemp[DATE=="1949-08-01", ma_13]

#6
ts_unemp <- ts(unemp$)

#7
ts_unrate<-ts(unrate$UNRATE, frequency=12, start=c(1948,1))


a_0.4 <- ses(ts_unrate, h=12, alpha=0.4, initial="simple")
accuracy(a_0.4)
a_0.9 <- ses(ts_unrate, h=12, alpha=0.9, initial="simple")
accuracy(a_0.4)

adf.test(ts_air)
adf.test(log(ts_air)) #계절 요인을 없애줌
adf.test(diff(ts_air))
