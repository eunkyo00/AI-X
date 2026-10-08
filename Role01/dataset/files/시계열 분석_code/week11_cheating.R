library(urca)
library(tsDyn)
library(vars)
library(zoo)
library(tseries)

# 1
data("EuStockMarkets")
adf.test(EuStockMarkets[,"DAX"], k = 0)

# 2
jo <- ca.jo(EuStockMarkets[,c("DAX", "SMI", "CAC")], type="trace", 
            ecdet="const", K=2)
summary(jo)

# 3
vecm <- VECM(EuStockMarkets[,c("DAX","SMI","CAC")], lag=1, r=1, 
             include="const", estim="ML")
summary(vecm)

# 4
ec_term <- residuals(vecm, type="invec")
plot(ec_term, main="Error-Correction Term")

# 5
var_from_vecm<-vec2var(jo, r=1)

# 6
irf1 <- irf(var_from_vecm, impulse="DAX", response="SMI", n.ahead=10)
plot(irf1)

# 예제
# 7
adf.test(EuStockMarkets[,"FTSE"], k = 0)

# 8, 9
jo1 <- ca.jo(EuStockMarkets[,c("DAX", "CAC", "FTSE")], type="trace", 
            ecdet="const", K=2)
summary(jo1)

# 10
vecm1 <- VECM(EuStockMarkets[,c("DAX", "CAC", "FTSE")], lag=2, r=1, 
              include="const", estim="ML")
summary(vecm1)
