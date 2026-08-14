"""Fundamental Analysis Engine for Indonesian Stocks.

Fetches and analyzes fundamental data including:
- Financial statements (Income Statement, Balance Sheet, Cash Flow)
- Financial ratios (PE, PBV, ROE, ROA, DER, etc.)
- Growth metrics (Revenue Growth, Earnings Growth)
- Valuation metrics (DCF, Comparable Analysis)
- Financial health scores

Data Sources:
- Yahoo Finance (yfinance)
- IDX Official (idx.co.id)
- Morningstar (morningstar.com)

Usage:
    from app.services.fundamental_analyzer import FundamentalAnalyzer
    
    analyzer = FundamentalAnalyzer()
    fundamentals = analyzer.analyze("BBCA")
    print(f"ROE: {fundamentals['profitability']['roe']}")
    print(f"PE Ratio: {fundamentals['valuation']['pe_ratio']}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────────

class SectorType(Enum):
    FINANCIAL = "Financials"
    CONSUMER = "Consumer Goods"
    INFRASTRUCTURE = "Infrastructure"
    MINING = "Mining"
    TECHNOLOGY = "Technology"
    PROPERTY = "Property & Real Estate"
    MANUFACTURING = "Manufacturing"
    TRADE_SERVICES = "Trade & Services"
    AGRICULTURE = "Agriculture"
    OTHER = "Other"


class FinancialHealth(Enum):
    VERY_STRONG = "VERY_STRONG"
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"
    VERY_WEAK = "VERY_WEAK"


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class FinancialRatios:
    """Key financial ratios."""
    # Profitability
    roe: Optional[float] = None  # Return on Equity
    roa: Optional[float] = None  # Return on Assets
    roic: Optional[float] = None  # Return on Invested Capital
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    
    # Valuation
    pe_ratio: Optional[float] = None  # Price to Earnings
    pb_ratio: Optional[float] = None  # Price to Book
    ps_ratio: Optional[float] = None  # Price to Sales
    peg_ratio: Optional[float] = None  # PE to Growth
    ev_ebitda: Optional[float] = None  # EV to EBITDA
    price_fcf: Optional[float] = None  # Price to Free Cash Flow
    
    # Financial Health
    debt_to_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None
    altman_z_score: Optional[float] = None
    
    # Efficiency
    asset_turnover: Optional[float] = None
    inventory_turnover: Optional[float] = None
    receivables_turnover: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GrowthMetrics:
    """Growth rate metrics."""
    revenue_growth_yoy: Optional[float] = None
    revenue_growth_3y_avg: Optional[float] = None
    revenue_growth_5y_avg: Optional[float] = None
    
    earnings_growth_yoy: Optional[float] = None
    earnings_growth_3y_avg: Optional[float] = None
    earnings_growth_5y_avg: Optional[float] = None
    
    eps_growth_yoy: Optional[float] = None
    eps_growth_3y_avg: Optional[float] = None
    eps_growth_5y_avg: Optional[float] = None
    
    book_value_growth_5y: Optional[float] = None
    fcff_growth_yoy: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinancialStatements:
    """Financial statement data."""
    # Income Statement
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    net_income: Optional[float] = None
    ebitda: Optional[float] = None
    eps: Optional[float] = None
    
    # Balance Sheet
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    cash_and_equivalents: Optional[float] = None
    total_debt: Optional[float] = None
    
    # Cash Flow
    operating_cash_flow: Optional[float] = None
    free_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    dividends_paid: Optional[float] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FundamentalResult:
    """Complete fundamental analysis result."""
    ticker: str
    company_name: str
    sector: str
    industry: str
    market_cap: float
    currency: str = "IDR"
    
    # Core data
    ratios: FinancialRatios = field(default_factory=FinancialRatios)
    growth: GrowthMetrics = field(default_factory=GrowthMetrics)
    financials: FinancialStatements = field(default_factory=FinancialStatements)
    
    # Scores (0-100)
    profitability_score: float = 0.0
    growth_score: float = 0.0
    valuation_score: float = 0.0
    financial_health_score: float = 0.0
    overall_score: float = 0.0
    
    # Ratings
    financial_health: str = "MODERATE"
    investment_grade: str = "HOLD"  # STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    
    # Metadata
    analysis_date: date = field(default_factory=date.today)
    fiscal_year_end: str = "December"
    
    def to_dict(self) -> dict:
        return asdict(self)


# ── Sector-Specific Weights ───────────────────────────────────────────────

SECTOR_WEIGHTS = {
    SectorType.FINANCIAL: {
        'profitability': 0.25,
        'growth': 0.20,
        'valuation': 0.25,
        'financial_health': 0.30,  # Banks need strong capital
    },
    SectorType.CONSUMER: {
        'profitability': 0.25,
        'growth': 0.30,
        'valuation': 0.25,
        'financial_health': 0.20,
    },
    SectorType.MINING: {
        'profitability': 0.30,
        'growth': 0.25,
        'valuation': 0.25,
        'financial_health': 0.20,
    },
    SectorType.TECHNOLOGY: {
        'profitability': 0.20,
        'growth': 0.40,  # Growth is key for tech
        'valuation': 0.20,
        'financial_health': 0.20,
    },
}

DEFAULT_WEIGHTS = {
    'profitability': 0.25,
    'growth': 0.25,
    'valuation': 0.25,
    'financial_health': 0.25,
}


# ── Fundamental Analyzer ──────────────────────────────────────────────────

class FundamentalAnalyzer:
    """Analyze fundamental data for Indonesian stocks."""
    
    # Sector mapping for IDX stocks
    IDX_SECTOR_MAP = {
        'BBCA': SectorType.FINANCIAL,
        'BBRI': SectorType.FINANCIAL,
        'BMRI': SectorType.FINANCIAL,
        'BBNI': SectorType.FINANCIAL,
        'BRIS': SectorType.FINANCIAL,
        'TLKM': SectorType.INFRASTRUCTURE,
        'EXCL': SectorType.INFRASTRUCTURE,
        'ISAT': SectorType.INFRASTRUCTURE,
        'UNVR': SectorType.CONSUMER,
        'ICBP': SectorType.CONSUMER,
        'INDF': SectorType.CONSUMER,
        'KLBF': SectorType.CONSUMER,
        'ADRO': SectorType.MINING,
        'PTBA': SectorType.MINING,
        'ANTM': SectorType.MINING,
        'INCO': SectorType.MINING,
        'GOTO': SectorType.TECHNOLOGY,
        'BUKA': SectorType.TECHNOLOGY,
        'EMTK': SectorType.TECHNOLOGY,
        'BSDE': SectorType.PROPERTY,
        'PWON': SectorType.PROPERTY,
        'SMRA': SectorType.PROPERTY,
    }
    
    def __init__(self):
        self._cache = {}
    
    def analyze(self, ticker: str, period: str = "2y") -> Optional[FundamentalResult]:
        """Run complete fundamental analysis on a stock.
        
        Parameters
        ----------
        ticker : str
            Stock ticker symbol (e.g., "BBCA")
        period : str
            Period for price data
        
        Returns
        -------
        FundamentalResult or None if analysis fails
        """
        logger.info(f"Starting fundamental analysis for {ticker}")
        
        try:
            # Fetch data from Yahoo Finance
            jk_ticker = f"{ticker}.JK"
            stock = yf.Ticker(jk_ticker)
            
            # Fetch all data
            info = self._fetch_stock_info(stock)
            if not info:
                return None
            
            # Get sector
            sector = self._get_sector(ticker, info.get('sector', ''))
            
            # Fetch financial statements
            financials = self._fetch_financials(stock)
            
            # Calculate ratios
            ratios = self._calculate_ratios(stock, info, financials)
            
            # Calculate growth metrics
            growth = self._calculate_growth(stock, financials)
            
            # Calculate scores
            weights = SECTOR_WEIGHTS.get(sector, DEFAULT_WEIGHTS)
            profitability_score = self._score_profitability(ratios)
            growth_score = self._score_growth(growth)
            valuation_score = self._score_valuation(ratios, sector)
            health_score = self._score_financial_health(ratios)
            
            # Overall score
            overall_score = (
                profitability_score * weights['profitability'] +
                growth_score * weights['growth'] +
                valuation_score * weights['valuation'] +
                health_score * weights['financial_health']
            )
            
            # Determine rating
            financial_health = self._determine_financial_health(health_score)
            investment_grade = self._determine_investment_grade(overall_score, growth_score)
            
            # Build result
            result = FundamentalResult(
                ticker=ticker,
                company_name=info.get('longName', info.get('shortName', ticker)),
                sector=sector.value,
                industry=info.get('industry', 'N/A'),
                market_cap=info.get('marketCap', 0) or 0,
                currency='IDR',
                ratios=ratios,
                growth=growth,
                financials=financials,
                profitability_score=round(profitability_score, 2),
                growth_score=round(growth_score, 2),
                valuation_score=round(valuation_score, 2),
                financial_health_score=round(health_score, 2),
                overall_score=round(overall_score, 2),
                financial_health=financial_health.value,
                investment_grade=investment_grade,
            )
            
            logger.info(
                f"Fundamental analysis complete for {ticker}: "
                f"Overall Score={overall_score:.1f}, Grade={investment_grade}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Fundamental analysis error for {ticker}: {e}")
            return None
    
    def _fetch_stock_info(self, stock: yf.Ticker) -> Optional[dict]:
        """Fetch stock info from Yahoo Finance."""
        try:
            info = stock.info
            if not info:
                return None
            
            return {
                'longName': info.get('longName'),
                'shortName': info.get('shortName'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'marketCap': info.get('marketCap'),
                'enterpriseValue': info.get('enterpriseValue'),
                'trailingPE': info.get('trailingPE'),
                'forwardPE': info.get('forwardPE'),
                'priceToBook': info.get('priceToBook'),
                'pegRatio': info.get('pegRatio'),
                'profitMargins': info.get('profitMargins'),
                'operatingMargins': info.get('operatingMargins'),
                'returnOnAssets': info.get('returnOnAssets'),
                'returnOnEquity': info.get('returnOnEquity'),
                'revenueGrowth': info.get('revenueGrowth'),
                'earningsGrowth': info.get('earningsGrowth'),
                'currentPrice': info.get('currentPrice') or info.get('regularMarketPrice'),
                'targetMeanPrice': info.get('targetMeanPrice'),
                'recommendationKey': info.get('recommendationKey'),
                'numberOfAnalystOpinions': info.get('numberOfAnalystOpinions'),
                'dividendYield': info.get('dividendYield'),
                'payoutRatio': info.get('payoutRatio'),
                'beta': info.get('beta'),
                'fiftyTwoWeekHigh': info.get('fiftyTwoWeekHigh'),
                'fiftyTwoWeekLow': info.get('fiftyTwoWeekLow'),
                'averageVolume': info.get('averageVolume'),
                'sharesOutstanding': info.get('sharesOutstanding'),
                'bookValue': info.get('bookValue'),
                'priceToSalesTrailing12Months': info.get('priceToSalesTrailing12Months'),
                'enterpriseToRevenue': info.get('enterpriseToRevenue'),
                'enterpriseToEbitda': info.get('enterpriseToEbitda'),
                'totalCash': info.get('totalCash'),
                'totalDebt': info.get('totalDebt'),
                'totalRevenue': info.get('totalRevenue'),
                'revenuePerShare': info.get('revenuePerShare'),
                'freeCashflow': info.get('freeCashflow'),
                'operatingCashflow': info.get('operatingCashflow'),
                'earningsQuarterlyGrowth': info.get('earningsQuarterlyGrowth'),
            }
        
        except Exception as e:
            logger.warning(f"Failed to fetch stock info: {e}")
            return None
    
    def _fetch_financials(self, stock: yf.Ticker) -> FinancialStatements:
        """Fetch financial statements."""
        financials = FinancialStatements()
        
        try:
            # Get income statement
            income_stmt = stock.financials
            if income_stmt is not None and not income_stmt.empty:
                latest = income_stmt.iloc[:, 0] if len(income_stmt.columns) > 0 else None
                if latest is not None:
                    financials.revenue = latest.get('Total Revenue')
                    financials.gross_profit = latest.get('Gross Profit')
                    financials.operating_income = latest.get('Operating Income')
                    financials.net_income = latest.get('Net Income')
                    financials.ebitda = latest.get('EBITDA')
            
            # Get balance sheet
            balance_sheet = stock.balance_sheet
            if balance_sheet is not None and not balance_sheet.empty:
                latest = balance_sheet.iloc[:, 0] if len(balance_sheet.columns) > 0 else None
                if latest is not None:
                    financials.total_assets = latest.get('Total Assets')
                    financials.total_liabilities = latest.get('Total Liabilities Net Minority Interest')
                    financials.total_equity = latest.get('Total Equity Gross Minority Interest')
                    financials.cash_and_equivalents = latest.get('Cash And Cash Equivalents')
                    financials.total_debt = latest.get('Total Debt')
            
            # Get cash flow
            cash_flow = stock.cashflow
            if cash_flow is not None and not cash_flow.empty:
                latest = cash_flow.iloc[:, 0] if len(cash_flow.columns) > 0 else None
                if latest is not None:
                    financials.operating_cash_flow = latest.get('Operating Cash Flow')
                    financials.capex = latest.get('Capital Expenditure')
                    financials.free_cash_flow = (
                        financials.operating_cash_flow + financials.capex
                        if financials.operating_cash_flow and financials.capex
                        else None
                    )
                    financials.dividends_paid = latest.get('Cash Dividends Paid')
            
            # EPS from info
            info = stock.info
            if info:
                financials.eps = info.get('trailingEps')
        
        except Exception as e:
            logger.warning(f"Failed to fetch financials: {e}")
        
        return financials
    
    def _calculate_ratios(
        self,
        stock: yf.Ticker,
        info: dict,
        financials: FinancialStatements
    ) -> FinancialRatios:
        """Calculate financial ratios."""
        ratios = FinancialRatios()
        
        # Directly from info
        ratios.pe_ratio = info.get('trailingPE')
        ratios.pb_ratio = info.get('priceToBook')
        ratios.ps_ratio = info.get('priceToSalesTrailing12Months')
        ratios.peg_ratio = info.get('pegRatio')
        ratios.ev_ebitda = info.get('enterpriseToEbitda')
        
        ratios.roe = info.get('returnOnEquity')
        ratios.roa = info.get('returnOnAssets')
        ratios.gross_margin = info.get('grossMargins')
        ratios.operating_margin = info.get('operatingMargins')
        ratios.net_margin = info.get('profitMargins')
        
        ratios.current_ratio = info.get('currentRatio')
        ratios.debt_to_equity = info.get('debtToEquity')
        
        # Calculate additional ratios
        if financials.total_debt and financials.total_equity:
            ratios.debt_to_equity = financials.total_debt / financials.total_equity
        
        if financials.operating_income and financials.total_debt:
            # Interest coverage (simplified)
            ratios.interest_coverage = financials.operating_income / (financials.total_debt * 0.1)
        
        if financials.free_cash_flow and info.get('marketCap'):
            ratios.price_fcf = info['marketCap'] / financials.free_cash_flow
        
        if financials.total_assets:
            ratios.asset_turnover = (
                financials.revenue / financials.total_assets
                if financials.revenue else None
            )
        
        # ROIC calculation
        if financials.operating_income and financials.total_equity and financials.total_debt:
            invested_capital = financials.total_equity + financials.total_debt
            ratios.roic = financials.operating_income / invested_capital
        
        return ratios
    
    def _calculate_growth(
        self,
        stock: yf.Ticker,
        financials: FinancialStatements
    ) -> GrowthMetrics:
        """Calculate growth metrics."""
        growth = GrowthMetrics()
        
        try:
            info = stock.info
            
            # YoY growth from info
            growth.revenue_growth_yoy = info.get('revenueGrowth')
            growth.earnings_growth_yoy = info.get('earningsGrowth')
            growth.eps_growth_yoy = info.get('earningsQuarterlyGrowth')
            
            # Historical growth calculation
            income_stmt = stock.financials
            if income_stmt is not None and len(income_stmt.columns) >= 2:
                # Revenue growth
                revenues = income_stmt.loc['Total Revenue'] if 'Total Revenue' in income_stmt.index else None
                if revenues is not None and len(revenues) >= 2:
                    growth.revenue_growth_yoy = (revenues.iloc[0] - revenues.iloc[1]) / revenues.iloc[1] if revenues.iloc[1] else None
                
                # Earnings growth
                net_income = income_stmt.loc['Net Income'] if 'Net Income' in income_stmt.index else None
                if net_income is not None and len(net_income) >= 2:
                    growth.earnings_growth_yoy = (net_income.iloc[0] - net_income.iloc[1]) / net_income.iloc[1] if net_income.iloc[1] else None
        
        except Exception as e:
            logger.warning(f"Failed to calculate growth: {e}")
        
        return growth
    
    def _get_sector(self, ticker: str, info_sector: str) -> SectorType:
        """Get sector for a stock."""
        # First try our mapping
        if ticker in self.IDX_SECTOR_MAP:
            return self.IDX_SECTOR_MAP[ticker]
        
        # Then try to map from info
        sector_map = {
            'Financial Services': SectorType.FINANCIAL,
            'Consumer Cyclical': SectorType.CONSUMER,
            'Consumer Defensive': SectorType.CONSUMER,
            'Technology': SectorType.TECHNOLOGY,
            'Basic Materials': SectorType.MINING,
            'Energy': SectorType.MINING,
            'Utilities': SectorType.INFRASTRUCTURE,
            'Communication Services': SectorType.INFRASTRUCTURE,
            'Real Estate': SectorType.PROPERTY,
            'Industrials': SectorType.MANUFACTURING,
        }
        
        return sector_map.get(info_sector, SectorType.OTHER)
    
    def _score_profitability(self, ratios: FinancialRatios) -> float:
        """Score profitability (0-100)."""
        score = 0.0
        factors = 0
        
        # ROE (0-25 points)
        if ratios.roe is not None:
            roe = ratios.roe * 100  # Convert to percentage
            if roe >= 20:
                score += 25
            elif roe >= 15:
                score += 20
            elif roe >= 10:
                score += 15
            elif roe >= 5:
                score += 10
            else:
                score += 5
            factors += 25
        
        # ROA (0-20 points)
        if ratios.roa is not None:
            roa = ratios.roa * 100
            if roa >= 10:
                score += 20
            elif roa >= 5:
                score += 15
            elif roa >= 3:
                score += 10
            else:
                score += 5
            factors += 20
        
        # Net Margin (0-20 points)
        if ratios.net_margin is not None:
            margin = ratios.net_margin * 100
            if margin >= 20:
                score += 20
            elif margin >= 15:
                score += 15
            elif margin >= 10:
                score += 10
            else:
                score += 5
            factors += 20
        
        # ROIC (0-20 points)
        if ratios.roic is not None:
            roic = ratios.roic * 100
            if roic >= 15:
                score += 20
            elif roic >= 10:
                score += 15
            elif roic >= 5:
                score += 10
            else:
                score += 5
            factors += 20
        
        # Gross Margin (0-15 points)
        if ratios.gross_margin is not None:
            gm = ratios.gross_margin * 100
            if gm >= 40:
                score += 15
            elif gm >= 30:
                score += 10
            else:
                score += 5
            factors += 15
        
        return (score / factors * 100) if factors > 0 else 50.0
    
    def _score_growth(self, growth: GrowthMetrics) -> float:
        """Score growth (0-100)."""
        score = 0.0
        factors = 0
        
        # Revenue Growth YoY (0-25 points)
        if growth.revenue_growth_yoy is not None:
            rev_growth = growth.revenue_growth_yoy * 100
            if rev_growth >= 20:
                score += 25
            elif rev_growth >= 15:
                score += 20
            elif rev_growth >= 10:
                score += 15
            elif rev_growth >= 5:
                score += 10
            else:
                score += 5
            factors += 25
        
        # Earnings Growth YoY (0-25 points)
        if growth.earnings_growth_yoy is not None:
            earn_growth = growth.earnings_growth_yoy * 100
            if earn_growth >= 20:
                score += 25
            elif earn_growth >= 15:
                score += 20
            elif earn_growth >= 10:
                score += 15
            elif earn_growth >= 5:
                score += 10
            else:
                score += 5
            factors += 25
        
        # EPS Growth (0-25 points)
        if growth.eps_growth_yoy is not None:
            eps_growth = growth.eps_growth_yoy * 100
            if eps_growth >= 20:
                score += 25
            elif eps_growth >= 15:
                score += 20
            elif eps_growth >= 10:
                score += 15
            elif eps_growth >= 5:
                score += 10
            else:
                score += 5
            factors += 25
        
        # FCF Growth (0-25 points)
        if growth.fcff_growth_yoy is not None:
            fcf_growth = growth.fcff_growth_yoy * 100
            if fcf_growth >= 15:
                score += 25
            elif fcf_growth >= 10:
                score += 20
            elif fcf_growth >= 5:
                score += 15
            else:
                score += 5
            factors += 25
        
        return (score / factors * 100) if factors > 0 else 50.0
    
    def _score_valuation(self, ratios: FinancialRatios, sector: SectorType) -> float:
        """Score valuation (0-100). Lower valuation = higher score."""
        score = 0.0
        factors = 0
        
        # Sector-specific PE benchmarks
        pe_benchmarks = {
            SectorType.FINANCIAL: 12,
            SectorType.CONSUMER: 18,
            SectorType.TECHNOLOGY: 25,
            SectorType.MINING: 10,
            SectorType.INFRASTRUCTURE: 15,
            SectorType.PROPERTY: 12,
        }
        benchmark_pe = pe_benchmarks.get(sector, 15)
        
        # PE Ratio (0-30 points)
        if ratios.pe_ratio is not None and ratios.pe_ratio > 0:
            pe_score = max(0, 30 * (1 - ratios.pe_ratio / (benchmark_pe * 2)))
            score += pe_score
            factors += 30
        
        # PB Ratio (0-25 points)
        if ratios.pb_ratio is not None and ratios.pb_ratio > 0:
            pb_benchmark = 2.0 if sector == SectorType.FINANCIAL else 3.0
            pb_score = max(0, 25 * (1 - ratios.pb_ratio / (pb_benchmark * 2)))
            score += pb_score
            factors += 25
        
        # PEG Ratio (0-25 points)
        if ratios.peg_ratio is not None and ratios.peg_ratio > 0:
            if ratios.peg_ratio < 1:
                score += 25  # Undervalued
            elif ratios.peg_ratio < 1.5:
                score += 20
            elif ratios.peg_ratio < 2:
                score += 15
            else:
                score += 5
            factors += 25
        
        # Price to FCF (0-20 points)
        if ratios.price_fcf is not None and ratios.price_fcf > 0:
            if ratios.price_fcf < 15:
                score += 20
            elif ratios.price_fcf < 25:
                score += 15
            elif ratios.price_fcf < 35:
                score += 10
            else:
                score += 5
            factors += 20
        
        return (score / factors * 100) if factors > 0 else 50.0
    
    def _score_financial_health(self, ratios: FinancialRatios) -> float:
        """Score financial health (0-100)."""
        score = 0.0
        factors = 0
        
        # Current Ratio (0-25 points)
        if ratios.current_ratio is not None:
            if ratios.current_ratio >= 2:
                score += 25
            elif ratios.current_ratio >= 1.5:
                score += 20
            elif ratios.current_ratio >= 1:
                score += 15
            else:
                score += 5  # Potential liquidity issues
            factors += 25
        
        # Debt to Equity (0-25 points)
        if ratios.debt_to_equity is not None:
            if ratios.debt_to_equity <= 0.5:
                score += 25
            elif ratios.debt_to_equity <= 1:
                score += 20
            elif ratios.debt_to_equity <= 2:
                score += 15
            else:
                score += 5  # High leverage
            factors += 25
        
        # Interest Coverage (0-25 points)
        if ratios.interest_coverage is not None:
            if ratios.interest_coverage >= 10:
                score += 25
            elif ratios.interest_coverage >= 5:
                score += 20
            elif ratios.interest_coverage >= 2:
                score += 15
            else:
                score += 5  # Potential default risk
            factors += 25
        
        # Altman Z-Score (0-25 points)
        if ratios.altman_z_score is not None:
            if ratios.altman_z_score > 3:
                score += 25  # Safe zone
            elif ratios.altman_z_score > 1.8:
                score += 15  # Grey zone
            else:
                score += 5  # Distress zone
            factors += 25
        
        return (score / factors * 100) if factors > 0 else 50.0
    
    def _determine_financial_health(self, health_score: float) -> FinancialHealth:
        """Determine financial health rating."""
        if health_score >= 80:
            return FinancialHealth.VERY_STRONG
        elif health_score >= 60:
            return FinancialHealth.STRONG
        elif health_score >= 40:
            return FinancialHealth.MODERATE
        elif health_score >= 20:
            return FinancialHealth.WEAK
        else:
            return FinancialHealth.VERY_WEAK
    
    def _determine_investment_grade(self, overall_score: float, growth_score: float) -> str:
        """Determine investment grade."""
        if overall_score >= 80 and growth_score >= 60:
            return "STRONG_BUY"
        elif overall_score >= 70:
            return "BUY"
        elif overall_score >= 50:
            return "HOLD"
        elif overall_score >= 30:
            return "SELL"
        else:
            return "STRONG_SELL"


# ── Formatting Utilities ──────────────────────────────────────────────────

def format_fundamental_summary(result: FundamentalResult) -> str:
    """Format fundamental analysis for display."""
    emoji_map = {
        'STRONG_BUY': '🟢',
        'BUY': '🟢',
        'HOLD': '🟡',
        'SELL': '🔴',
        'STRONG_SELL': '🔴',
        'VERY_STRONG': '🟢',
        'STRONG': '🟢',
        'MODERATE': '🟡',
        'WEAK': '🔴',
        'VERY_WEAK': '🔴',
    }
    
    lines = [
        f"┌───────────────────────────────────────────┐",
        f"│ 📊 {result.ticker} - Fundamental Analysis",
        f"├───────────────────────────────────────────┤",
        f"│ Company: {result.company_name[:35]:35s} │",
        f"│ Sector: {result.sector[:35]:35s} │",
        f"│ Market Cap: Rp {result.market_cap:>20,.0f} │" if result.market_cap else f"│ Market Cap: N/A {'':35s} │",
        f"├───────────────────────────────────────────┤",
        f"│ SCORES (0-100)".ljust(43) + "│",
        f"│   Profitability:    {result.profitability_score:5.1f} {'':10s} │",
        f"│   Growth:           {result.growth_score:5.1f} {'':10s} │",
        f"│   Valuation:        {result.valuation_score:5.1f} {'':10s} │",
        f"│   Financial Health: {result.financial_health_score:5.1f} {'':10s} │",
        f"│   ─────────────────────────────────────    │",
        f"│   OVERALL:          {result.overall_score:5.1f} {'':10s} │",
        f"├───────────────────────────────────────────┤",
        f"│ {emoji_map.get(result.investment_grade, '⚪')} Investment Grade: {result.investment_grade:20s} │",
        f"│ {emoji_map.get(result.financial_health, '⚪')} Financial Health: {result.financial_health:20s} │",
        f"└───────────────────────────────────────────┘",
    ]
    
    return "\n".join(lines)


# Singleton instance
fundamental_analyzer = FundamentalAnalyzer()
