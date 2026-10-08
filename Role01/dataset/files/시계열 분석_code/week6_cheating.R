library(zoo)
library(data.table)
library(tseries)
library(forecast)

# AR(1)
set.seed(123)
n<-100
phi1<-0.7
eps<-rnorm(n)
y_ar1 <- numeric(n)
y_ar1[1]<-10

for(t in 2:n) {
  y_ar1<-phi1*y_ar1[t-1]+eps[t]
}

plot(y_ar1, type='l', main="AR(1)")

acf(y_ar1)
pacf(y_ar1)
set.seed(123)
n<-100
phi1<-0.7
eps<-rnorm(n)
y_ar1 <- numeric(n)
y_ar1[1] <- 10

for (t in 2:n){
  y_ar1[t] <- phi1*y_ar1[t-1]+eps[t]
}

plot(y_ar1, type='l', main="AR(1)")

acf(y_ar1)
pacf(y_ar1)

# AR(2)
n<-100
phi1<-0.5
phi2<-0.2
eps<-rnorm(n)
y_ar2<-numeric(n)
y_ar2[1:2]<-c(10,12)

for (t in 3:n){
  y_ar2[t] <- phi1*y_ar2[t-1] + phi2*y_ar2[t-2] + eps[t]
}
plot(y_ar2, type='l', main="AR(2)")

acf(y_ar2)
pacf(y_ar2)

#RW
n<-100
eps<-rnorm(n)
y_rw<-numeric(n)
y_rw[1] <- 10

for(t in 2:n){
  y_rw[t] <-y_rw[t-1] + eps[t]
}
plot(y_rw, type='l', main='RW')

acf(y_rw)
pacf(y_rw)

acf(diff(y_rw))

#RW + drift
n<-100
drift<-0.5
eps<-rnorm(n)
y_rwd<-numeric(n)
y_rwd[1] <- 10

for(t in 2:n){
  y_rwd[t] <-drift + y_rwd[t-1] + eps[t]
}
plot(y_rwd, type='l', main='RW+drift')

acf(y_rwd)
pacf(y_rwd)

acf(diff(y_rwd))

# 과제
setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")

# 8 
nile<-fread("Lec6_Nile.csv")
str(nile)
nile_ts<-ts(nile$val, start=min(nile$year), frequency = 1)
str(nile_ts)
head(nile_ts)
plot(nile_ts)

# 9 
adf<-adf.test(nile_ts)
print(adf) # p=0.064, 귀무가설 기각x -> 비정상

# 10
fit<-auto.arima(nile_ts)
summary(fit)

# 11
checkresiduals(fit)

# 12
nile_forecast<-forecast(fit,h=10)
plot(nile_forecast)
