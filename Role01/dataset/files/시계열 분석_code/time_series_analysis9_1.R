# install.packages("rugarch")
# install.packages("FinTS")
library(FinTS)
library(rugarch)    # GARCH 모형 적합용  
library(tseries)    # ARCH LM 테스트용
library(forecast)   # ACF/PACF 및 plot

data("EuStockMarkets")
head(EuStockMarkets)
dax <- EuStockMarkets[, "DAX"]   # DAX 지수만 추출
ret_dax <- diff(log(dax)) * 100     # 일간로그수익률(%) 계산

spec <- ugarchspec( variance.model = list(model = "sGARCH", garchOrder = c(1,1)),
                    mean.model = list(armaOrder = c(0,0), include.mean = FALSE),
                    distribution.model = "std") 

#GARCH(1,1) 모형 사양 (평균은 0, 잔차는 Student-t 분포 가정)
fit <- ugarchfit(spec, data = ret_dax)
show(fit)  # 추정된 alpha0, alpha1, beta1 등 확인

std_resid <- residuals(fit, standardize=T)
Box.test(std_resid, lag = 20, type = "Ljung-Box")
ArchTest(std_resid, lags = 10)   #library(FinTS)
qqnorm(std_resid); qqline(std_resid)
fc <- ugarchforecast(fit, n.ahead = 10)
print(fc)

sigma_fc <- sigma(fc)
plot(sigma_fc, type="l")

# 예제
# 6
sp <- try(get.hist.quote("^GSPC", start="2020-01-01", end=Sys.Date(), 
                         quote="Close", provider="yahoo", retclass="zoo"),
          silent=T)
if (inherits(sp, "try-error")) stop("Network Problem.")

# 월간로그수익률(%) 계산
ret_sp <- diff(log(sp)) * 100
ret_sp <- na.omit(ret_sp)

spec_sp <- ugarchspec( variance.model = list(model = "sGARCH", garchOrder = c(1,1)),
                    mean.model = list(armaOrder = c(0,0), include.mean = FALSE),
                    distribution.model = "std")
fit_sp <- ugarchfit(spec_sp, data = ret_sp)
show(fit_sp)

# 7
std_resid <- residuals(fit_sp, standardize=T)
print(ArchTest(std_resid, lags=12))
print(Box.test(std_resid, lag=12,  type="Ljung-Box"))

fc_sp <- ugarchforecast(fit_sp, n.ahead=12)
sigma_fc<-sigma(fc_sp)
plot(sigma_fc, type='l')

