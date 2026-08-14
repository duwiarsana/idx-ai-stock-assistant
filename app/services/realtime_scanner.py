"""Real-time Stock Scanner & Alert System.

Continuously monitors all IDX stocks and sends instant alerts when
stocks meet bullish criteria based on technical + fundamental analysis.

Features:
- Scans all IDX stocks periodically
- Multi-factor analysis (Technical + Fundamental)
- Real-time alerting via Telegram
- Configurable scanning criteria
- Background scheduler
- Stock universe management

Usage:
    python -m app.services.realtime_scanner
    
    Or run as background service:
    nohup python -m app.services.realtime_scanner &
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable
import json
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.services.enhanced_technicals import EnhancedTechnicalEngine, TechnicalAnalysisResult
from app.services.fundamental_analyzer import FundamentalAnalyzer, FundamentalResult
from app.services.combined_analyzer import CombinedAnalyzer, CombinedAnalysisResult
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Enums ──────────────────────────────────────────────────────────────────

class AlertType(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    BREAKOUT = "BREAKOUT"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    DIVERGENCE = "DIVERGENCE"
    FUNDAMENTAL_UPGRADE = "FUNDAMENTAL_UPGRADE"


class ScanFrequency(Enum):
    REALTIME = "realtime"  # Every minute (during market hours)
    HIGH = "high"  # Every 5 minutes
    NORMAL = "normal"  # Every 15 minutes
    LOW = "low"  # Every hour
    EOD = "eod"  # End of day


# ── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class ScanCriteria:
    """Criteria for triggering alerts."""
    # Technical criteria
    min_technical_score: float = 60.0
    min_combined_score: float = 65.0
    require_buy_signal: bool = True
    min_volume_ratio: float = 1.5  # 150% of average
    require_uptrend: bool = False
    min_conviction: float = 0.6
    
    # Fundamental criteria
    min_fundamental_score: float = 50.0
    min_roe: float = 0.0  # 0%
    max_debt_equity: float = 3.0
    require_positive_earnings: bool = False
    
    # Alert settings
    alert_types: list = field(default_factory=lambda: [
        AlertType.STRONG_BUY.value,
        AlertType.BUY.value,
        AlertType.BREAKOUT.value,
    ])
    
    # Filters
    exclude_penny_stocks: bool = True
    min_price: float = 50  # IDR
    min_market_cap: float = 1_000_000_000  # 1B IDR
    
    def to_dict(self) -> dict:
        return {
            'min_technical_score': self.min_technical_score,
            'min_combined_score': self.min_combined_score,
            'require_buy_signal': self.require_buy_signal,
            'min_volume_ratio': self.min_volume_ratio,
            'require_uptrend': self.require_uptrend,
            'min_conviction': self.min_conviction,
            'min_fundamental_score': self.min_fundamental_score,
            'min_roe': self.min_roe,
            'max_debt_equity': self.max_debt_equity,
            'require_positive_earnings': self.require_positive_earnings,
            'exclude_penny_stocks': self.exclude_penny_stocks,
            'min_price': self.min_price,
            'min_market_cap': self.min_market_cap,
        }


@dataclass
class StockAlert:
    """Alert triggered when stock meets criteria."""
    ticker: str
    company_name: str
    alert_type: str
    timestamp: datetime
    price: float
    change_pct: float
    volume: int
    volume_ratio: float
    
    # Scores
    technical_score: float
    fundamental_score: float
    combined_score: float
    conviction: float
    
    # Signal details
    signal: str
    trend: str
    confidence: str
    
    # Key levels
    support: float
    resistance: float
    entry_zone: Optional[dict] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Metadata
    message: str = ""
    
    def to_dict(self) -> dict:
        return {
            'ticker': self.ticker,
            'company_name': self.company_name,
            'alert_type': self.alert_type,
            'timestamp': self.timestamp.isoformat(),
            'price': self.price,
            'change_pct': self.change_pct,
            'volume': self.volume,
            'volume_ratio': self.volume_ratio,
            'technical_score': self.technical_score,
            'fundamental_score': self.fundamental_score,
            'combined_score': self.combined_score,
            'conviction': self.conviction,
            'signal': self.signal,
            'trend': self.trend,
            'confidence': self.confidence,
            'support': self.support,
            'resistance': self.resistance,
            'entry_zone': self.entry_zone,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'message': self.message,
        }
    
    def to_telegram_message(self) -> str:
        """Format alert for Telegram - Minimal format with WHY reasoning."""
        emoji_map = {
            'STRONG_BUY': '🟢',
            'BUY': '🟢',
            'BREAKOUT': '🚀',
            'VOLUME_SPIKE': '📊',
            'DIVERGENCE': '🔄',
        }
        
        # Generate WHY reason (1 line summary)
        why_parts = []
        if self.technical_score >= 75:
            why_parts.append("Technical strong")
        if self.volume_ratio >= 2.0:
            why_parts.append(f"volume {self.volume_ratio:.1f}x")
        if self.conviction >= 0.7:
            why_parts.append("high conviction")
        if self.trend in ['UPTREND', 'STRONG_UPTREND']:
            why_parts.append("uptrend confirmed")
        if self.fundamental_score >= 70:
            why_parts.append("fundamental good")
        
        why_reason = " + ".join(why_parts[:3]) if why_parts else "Multiple signals aligned"
        
        # Calculate R/R
        rr_ratio = "N/A"
        if self.take_profit and self.stop_loss and self.price > self.stop_loss:
            rr_ratio = f"{((self.take_profit - self.price) / (self.price - self.stop_loss)):.1f}"
        
        # Format entry
        entry = f"{self.entry_zone['low']:,.0f}-{self.entry_zone['high']:,.0f}" if self.entry_zone else f"{self.price:,.0f}"
        
        # Format TP/SL
        tp_sl = f"\n   • TP: {self.take_profit:,.0f} | SL: {self.stop_loss:,.0f} | R/R: 1:{rr_ratio}" if self.take_profit and self.stop_loss else ""
        
        message = f"""
{emoji_map.get(self.alert_type, '🟡')} *{self.ticker}* - {self.company_name}
   Score: *{self.combined_score:.1f}/100* | Signal: *{self.signal}*
   Price: Rp {self.price:,.0f} ({self.change_pct:+.1f}%)

   📌 *Why:* {why_reason}

   💡 *Trade Plan:*
   • Entry: {entry}
{tp_sl}

⏰ {self.timestamp.strftime('%Y-%m-%d %H:%M')}
"""
        return message.strip()
    
    @staticmethod
    def create_multiple_alerts_message(alerts: list['StockAlert']) -> str:
        """Create a single message for multiple stock alerts."""
        from datetime import datetime
        
        if not alerts:
            return "No alerts found."
        
        # Sort by score
        sorted_alerts = sorted(alerts, key=lambda x: x.combined_score, reverse=True)
        
        # Header
        message = f"""
🚨 *STOCK ALERTS* - {len(sorted_alerts)} Opportunities Found
📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}

"""
        
        # Add each stock
        for i, alert in enumerate(sorted_alerts, 1):
            emoji = '🟢' if alert.combined_score >= 75 else '🟡' if alert.combined_score >= 65 else '⚪'
            
            # Generate WHY reason
            why_parts = []
            if alert.technical_score >= 75:
                why_parts.append("Technical strong")
            if alert.volume_ratio >= 2.0:
                why_parts.append(f"vol {alert.volume_ratio:.1f}x")
            if alert.conviction >= 0.7:
                why_parts.append("high conviction")
            if alert.trend in ['UPTREND', 'STRONG_UPTREND']:
                why_parts.append("uptrend")
            if alert.fundamental_score >= 70:
                why_parts.append("fundamental good")
            
            why_reason = " + ".join(why_parts[:3]) if why_parts else "Multiple signals"
            
            # Entry
            entry = f"{alert.entry_zone['low']:,.0f}-{alert.entry_zone['high']:,.0f}" if alert.entry_zone else f"{alert.price:,.0f}"
            
            # TP/SL with R/R
            tp_sl = ""
            if alert.take_profit and alert.stop_loss and alert.price > alert.stop_loss:
                rr = (alert.take_profit - alert.price) / (alert.price - alert.stop_loss)
                tp_sl = f"\n   • TP: {alert.take_profit:,.0f} | SL: {alert.stop_loss:,.0f} | R/R: 1:{rr:.1f}"
            
            message += f"""
━━━━━━━━━━━━━━━━━━━━

{i}. {emoji} *{alert.ticker}* - {alert.company_name}
   Score: *{alert.combined_score:.1f}/100* | Signal: *{alert.signal}*
   Price: Rp {alert.price:,.0f} ({alert.change_pct:+.1f}%)

   📌 *Why:* {why_reason}

   💡 *Trade Plan:*
   • Entry: {entry}
{tp_sl}

"""
        
        # Summary
        strong_buy = sum(1 for a in sorted_alerts if a.combined_score >= 75)
        buy = sum(1 for a in sorted_alerts if 65 <= a.combined_score < 75)
        watch = sum(1 for a in sorted_alerts if a.combined_score < 65)
        
        summary_parts = [f"🟢 Strong Buy: {strong_buy}"] if strong_buy else []
        if buy:
            summary_parts.append(f"🟡 Buy: {buy}")
        if watch:
            summary_parts.append(f"⚪ Watch: {watch}")
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━

📊 *Summary:*
{chr(10).join(summary_parts)}

⚠️ *DYOR - Do Your Own Research*
   Always use proper risk management (max 2-3% per trade)
"""
        
        return message.strip()


# ── IDX Stock Universe ────────────────────────────────────────────────────

class IDXStockUniverse:
    """Manages list of all IDX stocks."""
    
    # LQ45 stocks (most liquid) - priority scanning
    LQ45 = [
        'BBCA', 'BBRI', 'BMRI', 'BBNI', 'BRIS', 'BNLI',
        'TLKM', 'EXCL', 'ISAT',
        'ASII', 'INDF', 'UNVR', 'ICBP', 'KLBF', 'MYOR',
        'ADRO', 'PTBA', 'ANTM', 'INCO', 'ITMG',
        'GOTO', 'EMTK', 'BUKA',
        'BSDE', 'PWON', 'SMRA',
        'UNTR', 'HDFA',
        'WIKA', 'WSKT', 'WASK',
        'PGAS', 'AKRA',
        'SMGR',
        'GGRM',
        'HMSP',
        'JPFA',
        'TPIA',
        'BARO',
        'MEDC',
        'RALS',
        'MAPI',
        'ACES',
        'ERAA',
        'AMRT',
        'LINK',
        'TOWR',
        'SRTG',
        'DOID',
        'BOBA',
    ]
    
    # All IDX stocks (can be expanded)
    ALL_STOCKS = set(LQ45)
    
    @classmethod
    def get_priority_list(cls) -> list:
        """Get priority stocks for scanning (LQ45)."""
        return cls.LQ45.copy()
    
    @classmethod
    def get_all_stocks(cls) -> list:
        """Get all stocks in universe."""
        return list(cls.ALL_STOCKS)
    
    @classmethod
    def add_stock(cls, ticker: str):
        """Add stock to universe."""
        cls.ALL_STOCKS.add(ticker.upper())
    
    @classmethod
    def remove_stock(cls, ticker: str):
        """Remove stock from universe."""
        cls.ALL_STOCKS.discard(ticker.upper())


# ── Alert Handler ─────────────────────────────────────────────────────────

class AlertHandler:
    """Handles sending alerts via various channels."""
    
    def __init__(self):
        self.handlers = []
        self.alert_history = []
        self.cooldown = {}  # ticker -> last_alert_time
        self.cooldown_period = timedelta(minutes=30)  # Don't alert same stock twice in 30 min
    
    def register_handler(self, handler: Callable[[StockAlert], None]):
        """Register an alert handler (e.g., Telegram, email, webhook)."""
        self.handlers.append(handler)
    
    async def send_alert(self, alert: StockAlert):
        """Send alert through all registered handlers."""
        # Check cooldown
        if alert.ticker in self.cooldown:
            last_alert = self.cooldown[alert.ticker]
            if datetime.now() - last_alert < self.cooldown_period:
                logger.debug(f"Skipping alert for {alert.ticker} (cooldown)")
                return
        
        logger.info(f"🚨 ALERT: {alert.ticker} - {alert.alert_type} - {alert.message}")
        
        # Send through all handlers
        for handler in self.handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
        
        # Update cooldown
        self.cooldown[alert.ticker] = datetime.now()
        
        # Store in history
        self.alert_history.append(alert)
        
        # Limit history size
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-1000:]
    
    def save_alerts(self, filepath: str = "alert_history.json"):
        """Save alert history to file."""
        with open(filepath, 'w') as f:
            json.dump([a.to_dict() for a in self.alert_history], f, indent=2)


# ── Real-time Scanner ─────────────────────────────────────────────────────

class RealtimeScanner:
    """Real-time stock scanner with alerting."""
    
    def __init__(
        self,
        criteria: Optional[ScanCriteria] = None,
        frequency: ScanFrequency = ScanFrequency.NORMAL,
    ):
        self.criteria = criteria or ScanCriteria()
        self.frequency = frequency
        
        # Analysis engines
        self.technical_engine = EnhancedTechnicalEngine()
        self.fundamental_analyzer = FundamentalAnalyzer()
        self.combined_analyzer = CombinedAnalyzer()
        
        # Alert system
        self.alert_handler = AlertHandler()
        
        # State
        self.is_running = False
        self.scan_count = 0
        self.alert_count = 0
        self.last_scan_time = None
        self.scanned_stocks = {}
        
        # Market hours (WIB - Western Indonesian Time)
        self.market_open = 9  # 09:00 WIB
        self.market_close = 16  # 16:00 WIB
    
    def is_market_hours(self) -> bool:
        """Check if market is currently open."""
        now = datetime.now()
        
        # Weekend check
        if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
        
        # Market hours check (WIB)
        return self.market_open <= now.hour < self.market_close
    
    def get_scan_interval(self) -> int:
        """Get scan interval in seconds."""
        intervals = {
            ScanFrequency.REALTIME: 60,
            ScanFrequency.HIGH: 300,
            ScanFrequency.NORMAL: 900,
            ScanFrequency.LOW: 3600,
            ScanFrequency.EOD: 86400,
        }
        return intervals.get(self.frequency, 900)
    
    async def scan_stock(self, ticker: str) -> Optional[StockAlert]:
        """Scan a single stock and return alert if criteria met."""
        try:
            # Fetch price data
            jk_ticker = f"{ticker}.JK"
            stock = yf.Ticker(jk_ticker)
            
            # Get recent price data
            df = stock.history(period="1mo")
            
            if df.empty:
                return None
            
            df = df.reset_index()
            df.columns = df.columns.str.lower()
            
            # Quick filters
            current_price = df['close'].iloc[-1]
            
            # Price filter
            if self.criteria.exclude_penny_stocks and current_price < self.criteria.min_price:
                return None
            
            # Volume filter
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            current_volume = df['volume'].iloc[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            
            # Run technical analysis
            technical_result = self.technical_engine.analyze(df, ticker)
            
            if not technical_result:
                return None
            
            # Run fundamental analysis (cached)
            fundamental_result = self.fundamental_analyzer.analyze(ticker)
            
            # Run combined analysis
            combined_result = self.combined_analyzer.analyze(ticker, df)
            
            if not combined_result:
                return None
            
            # Check criteria
            alert = self._check_criteria(
                ticker=ticker,
                price_data=df,
                technical=technical_result,
                fundamental=fundamental_result,
                combined=combined_result,
                volume_ratio=volume_ratio,
            )
            
            return alert
        
        except Exception as e:
            logger.debug(f"Scan error for {ticker}: {e}")
            return None
    
    def _check_criteria(
        self,
        ticker: str,
        price_data: pd.DataFrame,
        technical: TechnicalAnalysisResult,
        fundamental: Optional[FundamentalResult],
        combined: CombinedAnalysisResult,
        volume_ratio: float,
    ) -> Optional[StockAlert]:
        """Check if stock meets alert criteria."""
        current_price = price_data['close'].iloc[-1]
        prev_close = price_data['close'].iloc[-2] if len(price_data) > 1 else current_price
        change_pct = ((current_price - prev_close) / prev_close * 100) if prev_close else 0
        current_volume = price_data['volume'].iloc[-1]
        
        # Check minimum scores
        if technical.composite_score < self.criteria.min_technical_score:
            return None
        
        if combined.combined_score < self.criteria.min_combined_score:
            return None
        
        if combined.conviction < self.criteria.min_conviction:
            return None
        
        # Check signal
        if self.criteria.require_buy_signal and technical.signal not in ['BUY', 'STRONG_BUY']:
            return None
        
        # Check trend
        if self.criteria.require_uptrend and technical.trend_direction not in ['UPTREND', 'STRONG_UPTREND']:
            return None
        
        # Check volume
        if volume_ratio < self.criteria.min_volume_ratio:
            return None
        
        # Check fundamental if available
        if fundamental:
            if fundamental.overall_score < self.criteria.min_fundamental_score:
                return None
            
            if fundamental.ratios.roe and fundamental.ratios.roe < self.criteria.min_roe:
                return None
            
            if fundamental.ratios.debt_to_equity and fundamental.ratios.debt_to_equity > self.criteria.max_debt_equity:
                return None
        
        # Determine alert type
        if combined.combined_score >= 75 and combined.conviction >= 0.8:
            alert_type = AlertType.STRONG_BUY.value
        elif technical.signal == 'BUY':
            alert_type = AlertType.BUY.value
        elif volume_ratio >= 3.0:
            alert_type = AlertType.VOLUME_SPIKE.value
        elif technical.divergences:
            alert_type = AlertType.DIVERGENCE.value
        else:
            alert_type = AlertType.BUY.value
        
        # Build alert
        support = technical.support_levels[0]['level'] if technical.support_levels else current_price * 0.95
        resistance = technical.resistance_levels[0]['level'] if technical.resistance_levels else current_price * 1.05
        
        alert = StockAlert(
            ticker=ticker,
            company_name=fundamental.company_name if fundamental else ticker,
            alert_type=alert_type,
            timestamp=datetime.now(),
            price=current_price,
            change_pct=change_pct,
            volume=current_volume,
            volume_ratio=volume_ratio,
            technical_score=technical.composite_score,
            fundamental_score=fundamental.overall_score if fundamental else 50.0,
            combined_score=combined.combined_score,
            conviction=combined.conviction,
            signal=technical.signal,
            trend=technical.trend_direction,
            confidence=combined.confidence,
            support=support,
            resistance=resistance,
            entry_zone=technical.entry_zone if hasattr(technical, 'entry_zone') else None,
            stop_loss=technical.stop_loss if hasattr(technical, 'stop_loss') else None,
            take_profit=technical.take_profit if hasattr(technical, 'take_profit') else None,
            message=f"{alert_type}: {ticker} @ Rp {current_price:,.0f} ({change_pct:+.1f}%)",
        )
        
        return alert
    
    async def scan_all_stocks(self) -> list[StockAlert]:
        """Scan all stocks in universe."""
        alerts = []
        stocks = IDXStockUniverse.get_priority_list()
        
        logger.info(f"🔍 Scanning {len(stocks)} stocks...")
        start_time = time.time()
        
        for i, ticker in enumerate(stocks, 1):
            # Progress logging
            if i % 10 == 0:
                logger.debug(f"Scanned {i}/{len(stocks)} stocks")
            
            alert = await self.scan_stock(ticker)
            
            if alert:
                alerts.append(alert)
                self.alert_count += 1
                logger.info(f"✅ Alert: {alert.ticker} - {alert.alert_type}")
        
        elapsed = time.time() - start_time
        logger.info(f"✅ Scan complete: {len(alerts)} alerts in {elapsed:.1f}s")
        
        self.scan_count += 1
        self.last_scan_time = datetime.now()
        self.scanned_stocks = {a.ticker: a for a in alerts}
        
        return alerts
    
    async def run_continuous(self):
        """Run scanner continuously."""
        self.is_running = True
        interval = self.get_scan_interval()
        
        logger.info(f"🚀 Starting real-time scanner (interval: {interval}s)")
        logger.info(f"📊 Scanning {len(IDXStockUniverse.get_priority_list())} stocks")
        logger.info(f"⚙️  Criteria: Min score={self.criteria.min_combined_score}, Min conviction={self.criteria.min_conviction}")
        
        while self.is_running:
            try:
                # Check market hours
                if self.is_market_hours():
                    alerts = await self.scan_all_stocks()
                    
                    # Send alerts
                    for alert in alerts:
                        await self.alert_handler.send_alert(alert)
                else:
                    logger.debug("Market closed - skipping scan")
                
                # Wait for next scan
                await asyncio.sleep(interval)
            
            except asyncio.CancelledError:
                logger.info("Scanner cancelled")
                break
            except Exception as e:
                logger.error(f"Scanner error: {e}")
                await asyncio.sleep(60)  # Wait 1 min on error
        
        self.is_running = False
        logger.info("Scanner stopped")
    
    def stop(self):
        """Stop the scanner."""
        self.is_running = False
        logger.info("Stopping scanner...")
    
    def get_status(self) -> dict:
        """Get scanner status."""
        return {
            'is_running': self.is_running,
            'scan_count': self.scan_count,
            'alert_count': self.alert_count,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'frequency': self.frequency.value,
            'interval_seconds': self.get_scan_interval(),
            'stocks_in_universe': len(IDXStockUniverse.get_priority_list()),
            'criteria': self.criteria.to_dict(),
        }


# ── Telegram Alert Integration ────────────────────────────────────────────

async def send_telegram_alert(alert: StockAlert):
    """Send single alert via Telegram bot (backward compatibility)."""
    try:
        from telegram import Bot
        
        bot_token = settings.telegram_bot_token
        if not bot_token:
            logger.warning("Telegram bot token not configured")
            return
        
        bot = Bot(token=bot_token)
        
        # Send to admin
        admin_id = settings.telegram_admin_id
        if admin_id:
            message = alert.to_telegram_message()
            await bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode='Markdown',
            )
            logger.info(f"Telegram alert sent for {alert.ticker}")
    
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")


async def send_telegram_batch_alert(alerts: list[StockAlert]):
    """Send batch of alerts as single message via Telegram bot."""
    try:
        from telegram import Bot
        
        bot_token = settings.telegram_bot_token
        if not bot_token:
            logger.warning("Telegram bot token not configured")
            return
        
        if not alerts:
            return
        
        bot = Bot(token=bot_token)
        
        # Send to admin
        admin_id = settings.telegram_admin_id
        if admin_id:
            # Use the new multiple alerts message format
            message = StockAlert.create_multiple_alerts_message(alerts)
            await bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True,
            )
            logger.info(f"Telegram batch alert sent: {len(alerts)} stocks")
    
    except Exception as e:
        logger.error(f"Telegram batch alert failed: {e}")


# ── Main Entry Point ──────────────────────────────────────────────────────

async def main():
    """Main function to run the scanner."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    )
    
    # Create scanner with custom criteria
    criteria = ScanCriteria(
        min_technical_score=60.0,
        min_combined_score=65.0,
        min_conviction=0.6,
        min_volume_ratio=1.5,
        require_buy_signal=True,
        min_fundamental_score=50.0,
    )
    
    scanner = RealtimeScanner(
        criteria=criteria,
        frequency=ScanFrequency.NORMAL,  # Scan every 15 minutes
    )
    
    # Register Telegram alert handler
    scanner.alert_handler.register_handler(send_telegram_alert)
    
    # Save alerts to file
    def save_alerts_handler(alert: StockAlert):
        scanner.alert_handler.save_alerts("alerts.json")
    
    scanner.alert_handler.register_handler(save_alerts_handler)
    
    try:
        # Run scanner
        await scanner.run_continuous()
    except KeyboardInterrupt:
        logger.info("Scanner interrupted by user")
        scanner.stop()


if __name__ == "__main__":
    asyncio.run(main())
