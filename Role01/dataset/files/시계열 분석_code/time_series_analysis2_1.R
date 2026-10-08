#install.packages("zoo")
#install.packages("data.table")
library(zoo)
library(data.table)

data <- rnorm(100)
head(data)
ts_data<-ts(data, frequency = 12, start = c(2020, 1))
head(ts_data)
plot(ts_data)
datetime <- as.POSIXct("2025-02-27 14:50:28",
                       format = "%Y-%m-%d %H:%M:%S", 
                       tz = "UTC")
OlsonNames()

data("AirPassengers")
str(AirPassengers)
plot(AirPassengers)
AirPassengers_d <- decompose(AirPassengers)
plot(AirPassengers_d)

data1 <- rnorm(10)
dates <- as.Date("2026-03-10")+0:9
date_z <- zoo(data1, order.by=dates)
plot(date_z)

dates1 <- as.Date("2026-03-13")+0:9
z1<-zoo(rnorm(10), order.by = dates)
z2<-zoo(rnorm(10), order.by = dates1)
merge(z1, z2)

lag_z1 <- lag(z1, k=2)
lag_z1
