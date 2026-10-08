library(data.table)
library(zoo)
library(lubridate)
library(ggplot2)
library(forecast)
library(tseries)
setwd("C:/Users/user/Desktop/hykim/시계열분석/data")
air <- fread("Lec4_AirPassengers.csv")
head(air)
setnames(air, c("V1","V2"), c("Date", "Passengers"))
ts_air <- ts(air$Passengers, frequency=12, start=c(1949,1))
holt_fit <- holt(ts_air, h=12, alpha=0.8, beta=0.01)
summary(holt_fit)
accuracy(holt_fit)
plot(holt_fit)
holt_fit1 <- holt(ts_air, h=12)
summary(holt_fit1)
plot(holt_fit1)

hw_add <- HoltWinters(ts_air, alpha=0.5, beta=0.03, gamma=0.8, 
                      seasonal="additive")
plot(hw_add)
forecast_add <- forecast(hw_add, h=12)
plot(forecast_add)
hw_add1 <- HoltWinters(ts_air, seasonal="additive")
forecast_add1 <- forecast(hw_add1, h=12)
summary(forecast_add1) #RMSE = 12.869
summary(forecast_add)

hw_mult <- HoltWinters(ts_air, seasonal="multiplicative") #a=0.276, b=0.033, g=0.871
forecast_mul <- forecast(hw_mult, h=12)
summary(forecast_mul) #RMSE = 11.204

par(mfrow=c(1,2))
plot(residuals(forecast_mul))
plot(residuals(forecast_add1))

acf(na.omit(residuals(forecast_mul)))
acf(na.omit(residuals(forecast_add1)))

#Ljung_Box 
Box.test(na.omit(residuals(forecast_mul)), lag=12, type="Ljung-Box")
Box.test(na.omit(residuals(forecast_add1)), lag=12, type="Ljung-Box")

par(mfrow=c(1,1))
#ACUTAL
plot(ts_air, type='l', col="black", 
     xlim=c(start(ts_air)[1], end(ts_air)[1]+2),
     ylim=c(min(ts_air), max(ts_air,forecast_mul$mean, forecast_add1$mean)+50),
     xlab="Time", ylab="Passengers")

#MULT - FITTING
lines(ts(hw_mult$fitted[,"xhat"], start=c(1950,1), frequency=frequency(ts_air)),
      col="red")
#MULT - FORECAST
lines(forecast_mul$mean, col="blue")

#ADDT - FITTING
lines(ts(hw_add1$fitted[,"xhat"], start=c(1950,1), frequency=frequency(ts_air)),
      col="green")
#ADDT - FORECAST
lines(forecast_add1$mean, col="orange")

#legend
legend("topleft", legend=c("Actual", "Mult - Fitted", "Mult - Forecast", 
                           "Add - Fitted", "Add - Forecast"), 
       col=c("black", "red", "blue", "green", "orange"), lty=1)

set.seed(123)
wn <- rnorm(200, mean=0, sd=1)
ts_wn <- ts(wn)

par(mfrow=c(2,2))
plot(ts_wn, main="white noise"); abline(h=0, col='red')
acf(ts_wn, main="acf")
hist(ts_wn, main="wn histogram")
qqnorm(ts_wn, main='qq-plot'); qqline(ts_wn, col='red')
Box.test(ts_wn, lag=10, type="Ljung-Box") #p-value = 0.4374

set.seed(321)
ts_ar1 <- arima.sim(model=list(ar=0.7), n=200)
plot(ts_ar1, main="ar(1)"); abline(h=0, col='red')
acf(ts_ar1, main="acf")
hist(ts_ar1, main="ar(1) histogram")
qqnorm(ts_ar1, main='qq-plot'); qqline(ts_ar1, col='red')
Box.test(ts_ar1, lag=10, type="Ljung-Box") #p-value < 2.2e-16

par(mfrow=c(3,1))
plot(ts_air, main="original")
plot(log(ts_air), main='log')
plot(diff(log(ts_air)), main='diff(log)'); abline(h=0, col='red')
