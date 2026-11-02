#install.packages("rugarch")
#install.packages("FinTS")
library(rugarch)
library(tseries)
library(forecast)
library(FinTS)

data("EuStockMarkets")
head(EuStockMarkets)
dax <- EuStockMarkets[,"DAX"]
ret_dax <- diff(log(dax))*100
plot(ret_dax)

spec <- ugarchspec( variance.model = list(model = "sGARCH", garchOrder = c(1,1)),
                    mean.model = list(armaOrder = c(0,0), include.mean = FALSE),
                    distribution.model = "std") 

fit <- ugarchfit(spec, data = ret_dax)
show(fit) 

std_resid <- residuals(fit, standardize = T)
Box.test(std_resid, lag=20, type="Ljung-Box") #잔차에 자기상관 X 
ArchTest(std_resid, lags=10) #ARCH 효과 X 
qqnorm(std_resid); qqline(std_resid)

fc <- ugarchforecast(fit, n.ahead=10)
print(fc)

sigma_fc <- sigma(fc)
plot(sigma_fc, type='l')

