library(lmtest)
library(vars)

phi1 <- matrix(c(0.3, -0.05, -0.1, 0.25), 2, 2, byrow=F)
phi2 <- matrix(c(0.2, -0.1, -0.75, 0.4), 2, 2, byrow=F)
F_val <- rbind(cbind(phi1,phi2),
               cbind(diag(2),matrix(0,2,2)))
eigen(F_val)$values


#4
phi1 <- matrix(c(0.31, -0.06, -0.11, 0.25), 2, 2, byrow=F)
phi2 <- matrix(c(0.22, -0.11, -0.77, 0.38), 2, 2, byrow=F)
F_val <- rbind(cbind(phi1,phi2),
               cbind(diag(2),matrix(0,2,2)))
eigen(F_val)$values

#6
data("EUStockMarkets")
df <- as.data.frame(EuStockMarkets)
head(df)

#과거 CAC가 FTSE 예측에 도움이 되는가?
grangertest(FTSE ~ CAC, order=7, data=df)

#과거 FTSE가 CAC 예측에 도움이 되는가?
grangertest(CAC ~ FTSE, order=7, data=df)

VARselect(df[,c("CAC","FTSE")], lag.max=14, type="const")
var_mod <- VAR(df[,c("CAC","FTSE")], lag.max=14, type="const")

#CAC->FTSE 인과관계 검정
causality(var_mod, cause="CAC")$Granger

#FTSE->CAC 인과관계 검정
causality(var_mod, cause="FTSE")$Granger

#8,9
var_mod2 <- VAR(df[,c("CAC","FTSE")],p=7,type="const")
causality(var_mod2, cause="CAC")$Granger
causality(var_mod2, cause="FTSE")$Granger

#10
var_mod1 <- VAR(df[,c("CAC","FTSE")],p=2,type="const")
causality(var_mod1, cause="CAC")$Granger
causality(var_mod1, cause="FTSE")$Granger