library(FinTS)
library(rugarch) # GARCH 모형 적합용
library(tseries) # ARCH LM 테스트용
library(forecast)

# GARCH 모형 실습 
data("EuStockMarkets")
head(EuStockMarkets)
dax <- EuStockMarkets[, "DAX"]  # DAX 지수만 추출
ret_dax <- diff(log(dax)) * 100  # 일간로그 수익률(%) 계산


# GARCH(1,1) 모형 설정 
spec <- ugarchspec(variance.model = list(model = "sGARCH", garchOrder = c(1,1)),
                   mean.model = list(armaOrder = c(0,0), include.mean = FALSE),
                   distribution.model = "std")
# GARCH(1,1) 모형 사양 (평균은 0, 잔차는 Student-t 분포 가정)

# 추정 결과 해석 
fit <- ugarchfit(spec, data = ret_dax)
show(fit) # 추정된 alpha0, alpha1, beta1 확인 

# 잔차 진단
# 표준화 잔차 추출
std_resid <- residuals(fit, standardize = TRUE)

# Ljung-Box Test(표준화 잔차)
# 백색 잡음 여부
Box.test(std_resid, lag=20, type = "Ljung-Box")

# ARCH LM Test
# 잔차 제곱의 자기상관 (ARCH 효과)
ArchTest(std_resid, lags = 10) #library(FinTS)

# 잔차 분포 확인(QQ Plot)
qqnorm(std_resid); qqline(std_resid)

# 변동성 예측 
# 향후 10일 앞까지 분산, 수익률을 예측
fc <- ugarchforecast(fit, n.ahead = 10)
print(fc)

# 예측된 조건부 표준편차(분산)의 시계열 그래프
sigma_fc <- sigma(fc)
plot(sigma_fc, type="l", main="Forecasted Conditional SD", ylab="Sigma")
# sqrt(a/1-a1-b1) = sqrt(0.0209/1-(0.078-0.905)) = 1.199%

# 예제
# 6, 7, 9
sp <- try(get.hist.quote("^GSPC", start="2020-01-01", end=Sys.Date(),
                         quote="Close", provider="yahoo", retclass="zoo"),
          silent = T)
if (inherits(sp, "try-error")) stop("Network Problem.")

# 월간 로그 수익률(%) 계산
ret_sp <- diff(log(sp)) * 100
ret_sp <- na.omit(ret_sp)

spec_sp <- ugarchspec(variance.model=list(model="sGARCH", sgarchorder=c(1,1)),
                       mean.model=list(armaOrder=c(0,0), include.mean=FALSE),
                       distribution.model="std")

fit_sp <- ugarchfit(spec_sp, data=ret_sp)
show(fit_sp)

# 8
std_resid <- residuals(fit_sp, standardize = T)
print(ArchTest(std_resid, lags = 12))
print(Box.test(std_resid, lag = 12, type = "Ljung-Box"))

# 10
fc_sp <- ugarchforecast(fit_sp, n.ahead=12)
sigma_fc <- sigma(fc_sp)
plot(sigma_fc, type='l')
print(sigma_fc)
