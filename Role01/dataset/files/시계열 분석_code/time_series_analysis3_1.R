setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")

#install.packages("lubridate")
library(data.table)
library(lubridate)

emails<-fread("Lec3_emails.csv")
emails[,week := as.Date(week)]

week_emails<-emails[, .(count_emails=.N), by=week]
all_dates<-seq(from=min(week_emails$week),
               to=max(week_emails$week),
               by="day")
setkey(week_emails, week)
upsampled<-week_emails[.(all_dates)]
upsampled[is.na(count_emails), count_emails := 0]
upsampled[,block:=floor((.I-1)/7)+1]
upsampled[,count_emails:={
  total<-sum(count_emails)
  avg<-total/.N
  val<-ceiling(avg)
  rep(val, .N)
}, by=block]

Sys.setlocale("LC_TIME", "C")
upsampled[,day:=weekdays(week)]
upsampled[week==as.Date("2015-02-09"),day]

ratio_map<-c(
  "Monday"=0.3, 
  "Tuesday"=0.15,
  "Wednesday"=0.15,
  "Thursday"=0.15,
  "Friday"=0.25,
  "Saturday"=0.00,
  "Sunday"=0.0
  )
upsampled[,ratio:=ratio_map[day]]

upsampled[, count_emails := {
  block_sum<-sum(count_emails, na.rm=T)
  new_vals <- ratio*block_sum
  new_vals <- ceiling(new_vals)
}, by=block]

unemp<-fread("Lec2_UNRATE.csv")
unemp[, DATE:=as.Date(DATE)]
unemp[seq.int(from=1, to=nrow(unemp), by=12)]
unemp[,mean(UNRATE), by=format(DATE,"%Y")] #"%Y-%m"
unemp[,.(avg_unrate=mean(UNRATE)), by=.(month=format(DATE,"%m"))]

donations<-fread("Lec3_donations.csv")
donations[,month:=floor_date(timestamp, "month")]
donations[,week:=floor_date(timestamp, "week")]
donations[order(month)]
donations[order(week)]

monthly_donations <- donations[, .(monthly_sum = sum(amount)), by = month]
monthly_donations <- monthly_donations[order(monthly_sum)]
tail(monthly_donations[order(monthly_sum)])

monthly_don_avg <- donations[, .(monthly_avg = mean(amount)), by = month]
monthly_don_avg <- monthly_don_avg[order(monthly_avg)]
monthly_don_avg <-(order(monthly_avg))

donations[,week_mon:=floor_date(timestamp, "week",week_Start=1)]
weekly_donations_mon<-donations[, .(weekly_sum_mon(amount)),by=week]
weekly_donations_mon[order(weekly_sum_mon)]

# 평균 실업률
unemp<-fread("Lec2_UNRATE.csv")
unemp[,DATE:=as.Date(DATE)]
unemp[,quarter:=paste0(format(DATE,"%Y"),"Q",
                      ceiling(as.integer(format(DATE, "%m"))/3))]

quarterly<-unemp[,.(avg_unrate=mean(UNRATE)), by=quarter]
bad<-unemp[UNRATE>7]
nrow(bad)
mean(bad$UNRATE)

ts_unemp<-ts(unemp$UNRATE, start=c(1948,1), frequency=12)
fit<-stl(ts_unemp, s.window="periodic")
plot(fit)
