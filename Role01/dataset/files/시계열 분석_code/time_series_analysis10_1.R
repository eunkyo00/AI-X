library(lmtest)
library(vars)

data("EuStockMarkets")
df<-as.data.frame(EuStockMarkets)
head(df)

grangertest(SMI~DAX, order=5, data=df)

grangertest(DAX~SMI, order=5, data=df)

VARselect(df[,c("DAX", "SMI")], lag.max = 10, type = "const")

var_mod <- VAR(df[,c("DAX", "SMI")], p=2, type="const")
var_mod

causality(var_mod, cause="DAX")$Granger
causality(var_mod, cause="SMI")$Granger
