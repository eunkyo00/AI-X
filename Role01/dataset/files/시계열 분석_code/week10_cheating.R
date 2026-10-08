library(lmtest)
library(vars)

# VAR 모형 전제: 정상성 검정
phi1 <- matrix(c(0.3, -0.05, -0.1, 0.25), 2, 2, byrow=F)
phi2 <- matrix(c(0.2, -0.1, -0.75, 0.4), 2, 2, byrow=F)
F_val <- rbind(cbind(phi1,phi2),
               cbind(diag(2),matrix(0,2,2)))
eigen(F_val)$values

# Granger Causality
data("EustockMarkets")
df <- as.data.frame(EuStockMarkets)
head(df)

# DAX -> SMI
grangertest(SMI~DAX, order=5, data=df)
# SMI -> DAX
grangertest(DAX~SMI, order=5, data=df)

# 최적의 시차 선택 
VARselect(df[,c("DAX", "SMI")], lag.max=10, type="const")

# VAR 모형 추정 
var_mod <- VAR(df[,c("DAX", "SMI")], p=2, type="const")

# 인과관계 검정 
causality(var_mod, cause="DAX")$Granger
causality(var_mod, cause="SMI")$Granger

# 4 
phi1 <- matrix(c(0.31, -0.06, -0.11, 0.25), 2, 2, byrow=F)
phi2 <- matrix(c(0.22, -0.11, -0.77, 0.38), 2, 2, byrow=F)
F_val <- rbind(cbind(phi1, phi2),
               cbind(diag(2), matrix(0,2,2)))
eigen(F_val)$values

# 6, 7
# 과거 CAC가 FTSE 예측에 도움이 되는가?
grangertest(FTSE~CAC, order=7, data=df)

# 과거 FTSE가 CAC 예측에 도움이 되는가?
grangertest(CAC~FTSE, order=7, data=df)

VARselect(df[,c("CAC", "FTSE")], lag.max=14, type="const")
var_mod1 <- VAR(df[,c("CAC", "FTSE")], lag.max=14, type="const")

# CAC -> FTSE 인과관계 검정
causality(var_mod1, cause="CAC")$Granger

# FTSE -> CAC 인과관계 검정
causality(var_mod1, cause="FTSE")$Granger

# 8, 9
var_mod2 <- VAR(df[,c("CAC", "FTSE")], p=7, type="const")
causality(var_mod2, cause="CAC")$Granger
causality(var_mod2, cause="FTSE")$Granger

# 10
var_mod3 <- VAR(df[,c("CAC", "FTSE")], p=2, type="const")
causality(var_mod3, cause="CAC")$Granger
causality(var_mod3, cause="FTSE")$Granger
