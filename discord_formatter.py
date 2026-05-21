import discord


class DiscordFormatter:
    @staticmethod
    def format_item(item):
        source = item.get('source', 'Unknown')
        color = {
            'Twitter': 0x1DA1F2,
            'TikTok': 0x111111,
            'Website': 0xE85D9E,
            'Tumblr': 0x36465D,
            'Instagram': 0xDD2A7B,
            'Spotify': 0x1DB954,
            'Apple Music': 0xFA243C,
            'SoundCloud': 0xFF5500,
            'YouTube': 0xFF0000,
        }.get(source, 0xE85D9E)

        if source == 'Website':
            color = 0x2ECC71 if item.get('event_type') == 'restocked' else 0xE85D9E

        title = f"New {source} update"
        if source == 'Website':
            event_type = item.get('event_type', 'new')
            prefix = "Back in stock" if event_type == 'restocked' else "Product update"
            title = f"{prefix}: {item.get('title', 'Rimera product')}"
        elif item.get('title'):
            title = item['title']

        title = DiscordFormatter._truncate(title, 256)
        description = DiscordFormatter._truncate(
            item.get('description') or item.get('content', 'No description available.'),
            3500
        )

        embed = discord.Embed(
            title=title,
            description=description,
            url=item.get('url', ''),
            color=color
        )

        if source == 'Website' and 'title' in item:
            status = "Sold out" if item.get('sold_out') else "In stock"
            embed.add_field(name="Status", value=status, inline=True)

            if item.get('price'):
                embed.add_field(name="Price", value=item['price'], inline=True)

            if item.get('variants_total') is not None:
                variant_text = f"{item.get('variants_available', 0)} of {item.get('variants_total', 0)} available"
                embed.add_field(name="Variants", value=variant_text, inline=True)

        if item.get('image_url'):
            embed.set_image(url=item['image_url'])

        embed.set_footer(text=f"Rimera Bot | {source}")
        if item.get('timestamp'):
            embed.set_author(name=DiscordFormatter._truncate(item['timestamp'], 256))

        return embed

    @staticmethod
    def _truncate(value, limit):
        text = str(value or '')
        if len(text) <= limit:
            return text
        return f"{text[:limit - 3]}..."
