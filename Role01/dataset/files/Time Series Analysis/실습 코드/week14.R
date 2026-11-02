library(lubridate)
library(forecast)
library(vars)
library(tidyr)
library(dplyr)
setwd("~/Week14_Data")
flu <- read.csv("Lec14_french_flu.csv")
tail(flu)

flu$year <- substr(flu$week, 1, 4)
flu$week_num <- substr(flu$week, 5, 6)
flu$date <- as.Date(paste0(flu$year, "-", flu$week_num, "-1"), format="%Y-%U-%u")

alsace <- flu[flu$region_name=="ALSACE",]
alsace <- alsace[order(alsace$date),]

alsace$TauxGrippe <- as.numeric(alsace$TauxGrippe)
ts_alsace <- ts(alsace$TauxGrippe, frequency=52)

fit_arima <- auto.arima(ts_alsace)
summary(fit_arima)

forecast_arima <- forecast(fit_arima, h=12)
plot(forecast_arima)

selected_regions <- c("ALSACE", "ILE-DE-FRANCE", "RHONE-ALPES", "PROVENCE-ALPES-COTE-D-AZUR", "NORD-PAS-DE-CALAIS")
flu$TauxGrippe <- as.numeric(flu$TauxGrippe)   ####### 여기! ######
flu_wide <- flu %>% filter(region_name %in% selected_regions) %>% 
  select(date, region_name, TauxGrippe) %>% 
  pivot_wider(names_from=region_name, values_from=TauxGrippe, values_fn=mean) %>%
  arrange(date)
tail(flu_wide)

