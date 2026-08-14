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
        
        why_reason = " + ".join(why_parts[:3]) if why_parts else "Multiple signals aligned"
        
        # Format TP/SL
        tp_sl = ""
        if self.take_profit and self.stop_loss:
            tp_sl = f"\n   • TP: {self.take_profit:,.0f} | SL: {self.stop_loss:,.0f}"
        
        message = f"""
{emoji_map.get(self.alert_type, '🟡')} *{self.ticker}* - {self.company_name}
   Score: *{self.combined_score:.1f}/100* | Signal: *{self.signal}*
   Price: Rp {self.price:,.0f} ({self.change_pct:+.1f}%)

   📌 *Why:* {why_reason}

   💡 *Trade Plan:*
   • Entry: {self.entry_zone['low']:,.0f}-{self.entry_zone['high']:,.0f} if self.entry_zone else f"{self.price:,.0f}"}
{tp_sl}
   • R/R: 1:{((self.take_profit - self.price) / (self.price - self.stop_loss)):.1f} if self.take_profit and self.stop_loss else "N/A"}

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
            
            # TP/SL
            tp_sl = ""
            if alert.take_profit and alert.stop_loss:
                rr = (alert.take_profit - alert.price) / (alert.price - alert.stop_loss)
                tp_sl = f"\n   • TP: {alert.take_profit:,.0f} | SL: {alert.stop_loss:,.0f} | R/R: 1:{rr:.1f}"
            
            message += f"""
━━━━━━━━━━━━━━━━━━━━

{i}. {emoji} *{alert.ticker}* - {alert.company_name}
   Score: *{alert.combined_score:.1f}/100* | Signal: *{alert.signal}*
   Price: Rp {alert.price:,.0f} ({alert.change_pct:+.1f}%)

   📌 *Why:* {why_reason}

   💡 *Trade Plan:*
   • Entry: {alert.entry_zone['low']:,.0f}-{alert.entry_zone['high']:,.0f} if alert.entry_zone else f"{alert.price:,.0f}"}
{tp_sl}

"""
        
        # Summary
        strong_buy = sum(1 for a in sorted_alerts if a.combined_score >= 75)
        buy = sum(1 for a in sorted_alerts if 65 <= a.combined_score < 75)
        watch = sum(1 for a in sorted_alerts if a.combined_score < 65)
        
        message += f"""
━━━━━━━━━━━━━━━━━━━━

📊 *Summary:*
🟢 Strong Buy: {strong_buy}
🟡 Buy: {buy}
{"⚪ Watch: " + str(watch) if watch > 0 else ""}

⚠️ *DYOR - Do Your Own Research*
   Always use proper risk management (max 2-3% per trade)
"""
        
        return message.strip()
