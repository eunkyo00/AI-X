# install.packages("dlm")
library(lubridate)
library(forecast)
library(vars)
library(dplyr)
library(tidyr)
library(dlm)
setwd("C:/Users/User/Desktop/시계열분석/시계열분석 데이터")
flu <- read.csv("Lec14_french_flu.csv")
head(flu)

flu$year <- substr(flu$week, 1, 4)
flu$week_num <- substr(flu$week, 5, 6)
flu$date <- as.Date(paste0(flu$year,"-", flu$week_num, "-1"), format="%Y-%U-%u")

alsace <- flu[flu$region_name=="ALSACE",]
alsace <- alsace[order(alsace$date),]

alsace$TauxGrippe <- as.numeric(alsace$TauxGrippe)
ts_alsace <- ts(alsace$TauxGrippe, frequency=52)

fit_arima <- auto.arima(ts_alsace)
summary(fit_arima)

forecast_arima <- forecast(fit_arima, h=12)
plot(forecast_arima)

selected_regions <- c("ALSACE", "ILE-DE-FRANCE", "RHONE-ALPES")
flu$TauxGrippe <- as.numeric(flu$TauxGrippe)
flu_wide <- flu %>% filter(region_name %in% selected_regions) %>% 
  select(date, region_name, TauxGrippe) %>%
  pivot_wider(names_from=region_name, values_from=TauxGrippe, values_fn=mean)%>%
  arrange(date)
tail(flu_wide)

flu_wide <- flu_wide %>% fill(everything(), .direction="downup")
flu_var <- ts(flu_wide[,-1], start=c(2013,1), frequency=52)
flu_var <- VAR(flu_var, ic="AIC", type="const")
summary(flu_var)

flu$year <- substr(flu$week, 1, 4)
flu$week_num <- substr(flu$week, 5, 6)
flu$date <- as.Date(paste0(flu$year,"-", flu$week_num, "-1"), format="%Y-%U-%u")

alsace <- flu[flu$region_name=="ALSACE",]
alsace <- alsace[order(alsace$date),]
alsace$TauxGrippe <- as.numeric(alsace$TauxGrippe)
Y <- alsace$TauxGrippe

build_dlm <- function(par){
  dlmModPoly(order=2, dV=exp(par[1]), dW=exp(par[2:3]))
}
init_par <- log(c(var(Y, na.rm=T), 1,1e-2))

fit <- dlmMLE(Y, parm=init_par, build=build_dlm)
mod_fitted <- build_dlm(fit$par)
filtered <- dlmFilter(Y, mod_fitted)
y_hat <- drop(filter$f)
resid <- Y-y_hat

data.frame(Date=head(alsace$date, length(y_hat)),
           Actual=round(head(Y, length(y_hat)),1),
           Forecast=round(pmax(y_hat,0),1),
           Residual=round(Y-max(y_hat,0),1))
plot(result$Date, result$Actual, type="l",
     ylim=range(result$Actual, result$Forecast))
lines(result$DAte, result$Forecast, col="blue", lty=2)

apple <- read.csv("apple.csv", stringsAsFactors = FALSE)

# sales 열의 쉽표제거 후 
apple<-read.csv("apple.csv")
