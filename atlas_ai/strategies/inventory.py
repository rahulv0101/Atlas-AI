"""Shared strategy inventory; construction preserves runtime order and defaults."""
from atlas_ai.strategies.built_in import (EMACrossoverStrategy,RSIMeanReversionStrategy,
    BreakoutStrategy,CandlestickPatternStrategy,EMACrossoverClosedConfirmMidExitStrategy)
from atlas_ai.strategies.minute_pack import (MACDTrendStrategy,BollingerMeanReversionStrategy,
    StochasticReversalStrategy,VWAPProxyReversionStrategy,MomentumContinuationStrategy,
    PullbackTrendStrategy,RSITrendHybridStrategy,GoldMicroImpulseStrategy,GoldBreakoutRetestStrategy,
    GoldLiquiditySweepStrategy,GoldMicroStructureReversionStrategy,PullbackTrendM15MidExitStrategy)


def base_inventory(timeframe,*,paper_variants=False):
    strategies=[EMACrossoverStrategy(),RSIMeanReversionStrategy(),BreakoutStrategy(),CandlestickPatternStrategy(),
        MACDTrendStrategy(),BollingerMeanReversionStrategy(),StochasticReversalStrategy(),
        VWAPProxyReversionStrategy(),MomentumContinuationStrategy(),PullbackTrendStrategy(),RSITrendHybridStrategy()]
    if str(timeframe).upper()=="M1":
        strategies.extend([GoldMicroImpulseStrategy(),GoldBreakoutRetestStrategy(),
            GoldLiquiditySweepStrategy(),GoldMicroStructureReversionStrategy()])
    if str(timeframe).upper()=="M15" and paper_variants:
        strategies.extend([EMACrossoverClosedConfirmMidExitStrategy(),PullbackTrendM15MidExitStrategy()])
    return strategies
