#install.packages("zoo")
#install.packages("data.table")
library(zoo)
library(data.table)

setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
data <- rnorm(100)
head(data)
ts_data <- ts(data, frequency=12, start=c(2020,1))
head(ts_data)
plot(ts_data)
datetime <- as.POSIXct("2025-02-27 14:50:28",
                       format="%Y-%m-%d %H:%M:%S",
                       tz="UTC")
datetime
OlsonNames()

data("AirPassengers")
str(AirPassengers)
plot(AirPassengers)
AirPassengers_d <- decompose(AirPassengers)
plot(AirPassengers_d)

data1 <- rnorm(10)
dates <- as.Date("2026-03-10")+0:9
data_z <- zoo(data1, order.by=dates)
plot(data_z)
dates1 <- as.Date("2026-03-13")+0:9
z1 <- zoo(rnorm(10), order.by = dates)
z2 <- zoo(rnorm(10), order.by = dates1)
merge(z1,z2)

lag_z1 <- lag(z1, k=2)
lag_z1

dt1 <- data.table(time=as.POSIXct(c("2025-01-01 00:00:00",
                                    "2025-01-01 01:00:00",
                                    "2025-01-01 02:00:00",
                                    "2025-01-01 03:00:00")),
                  temperature = c(10,12,11,13))
dt2 <- data.table(time=as.POSIXct(c("2025-01-01 00:30:00",
                                    "2025-01-01 01:45:00",
                                    "2025-01-01 02:15:00")),
                  humidity = c(70,65,68))
setkey(dt1, time)
setkey(dt2, time)

result <- dt1[dt2, roll=T]
print(result)

z_temp <- zoo(result$temperature, order.by=result$time)
z_hum <- zoo(result$humidity, order.by=result$time)

time <- 1:10 
value <- c(10, 12, NA, NA, 18, 20, NA, 25, 27, 30)
data <- data.frame(time, value)
data
#linear interpolation 
linear <- approx(data$time, data$value, xout=data$time)
linear
#spline interpolation
spli <- spline(data$time, data$value, xout=data$time)
spli

unemp <- fread("Lec2_UNRATE.csv")
unemp[, DATE := as.Date(DATE)]
setkey(unemp, DATE)
missing_sample <- scan("Lec2_sample.txt", what=integer())
unemp_missing <- unemp[-missing_sample]
missing_sample_high <- scan("Lec2_sample_high.txt", what=integer())
unemp_missing_high <- unemp[-missing_sample_high]

all_dates <- seq(from=unemp$DATE[1], to=tail(unemp$DATE,1), by="months")

unemp_missing <- unemp_missing[J(all_dates), roll=0]
unemp_missing_high <- unemp_missing_high[J(all_dates), roll=0]

unemp_missing[, rpt := is.na(UNRATE)]
unemp_missing_high[, rpt := is.na(UNRATE)]

unemp_missing[, impute_ff := na.locf(UNRATE, na.rm=F)]
unemp_missing_high[, impute_ff := na.locf(UNRATE, na.rm=F)]

unemp[300:400, plot(DATE, UNRATE, col=1, type='b')]
unemp_missing[300:400, lines(DATE, impute_ff, col=2)]
unemp_missing[300:400][rpt==T, points(DATE, impute_ff, col=2, pch=24)]

unemp[300:400, plot(DATE, UNRATE, col=1, type='b')]
unemp_missing_high[300:400, lines(DATE, impute_ff, col=3)]
unemp_missing_high[300:400][rpt==T, points(DATE, impute_ff, col=3, pch=19)]