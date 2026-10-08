setwd("C:/Users/User/Desktop/시계열분석 데이터")

library(data.table)
library(zoo)

dt1 <-data.table(
  time = as.POSIXct(c("2025-01-01 00:00:00", 
                      "2025-01-01 01:00:00",
                      "2025-01-01 02:00:00",
                      "2025-01-01 03:00:00")),
  value1 = c(10, 12, 11, 13))
dt2 <-data.table(
  time = as.POSIXct(c("2025-01-01 00:03:00",
                      "2025-01-01 01:45:00",
                      "2025-01-01 02:15:00")),
  value2 = c(70, 65, 68))

setkey(dt1, time)
setkey(dt2, time)

result <- dt1[dt2, roll = TRUE]
print(result)

z_temp <- zoo(result$temperature, order.by = result$time)
z_hum <- zoo(result$humidity, order.by = result$time)

time<-1:10
value<-c(10, 12, NA, NA, 18, 20, NA, 25, 27, 30)
data<-data.frame(time, value)

#linear intepolation
linear <- approx(data$time, data$value, xout=data$time)

#spline interpolation
spli <- spline(data$time, data$value, xout=data$time)

unemp<-fread("Lec2_UNRATE.csv")
unemp[, DATE := as.Date(DATE)]
setkey(unemp, DATE)
missing_sample<-scan("Lec2_sample.txt", what=integer())
unemp_missing<-unemp[-missing_sample]
missing_sample_high<-scan("Lec2_sample_high.txt", what=integer())
unemp_missing_high<-unemp[-missing_sample_high]

all_dates<-seq(from=unemp$DATE[1], to=tail(unemp$DATE,1), by="months")

unemp_missing<-unemp_missing[J(all_dates), roll=0]
unemp_missing_high<-unemp_missing[J(all_dates), roll=0]
unemp_missing[, rpt := is.na(UNRATE)]
unemp_missing_high[, rpt := is.na(UNRATE)]

unemp_missing[, impute_ff := na.locf(UNRATE, na.rm=FALSE)]
unemp_missing_high[, impute_ff := na.locf(UNRATE, na.rm=FALSE)]

unemp[300:400, plot(DATE, UNRATE, col=1, type='b')]
unemp_missing[300:400, lines(DATE, impute_ff, col=2)]
unemp_missing[300:400][rpt==T, points(DATE, impute_ff, col=2, pch=24)]

unemp[300:400, plot(DATE, UNRATE, col=1, type='b')]
unemp_missing_high[300:400, lines(DATE, impute_ff, col=3)]
unemp_missing_high[300:400][rpt==T, points(DATE, impute_ff, col=3, pch=19)]

