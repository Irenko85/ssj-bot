import discord
from utils import utils
from db import db
from discord.ext import commands, tasks


class WCA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.default_country = "Chile"
        self.language = "es"
        self.channel = None

    def cog_unload(self):
        # Stop the competition check task when the cog is unloaded
        self.check_new_competitions.cancel()

    def set_channel(self, channel):
        """
        Sets the channel for sending competition notifications.

        Parameters:
        - channel: Discord channel object.

        Returns:
        - None
        """
        self.channel = channel
        if not self.check_new_competitions.is_running():
            self.check_new_competitions.start()

    @commands.command(
        name="set-country", help="Sets the default country.", aliases=["sc"]
    )
    async def set_country(self, ctx, *args):
        """
        Command to set the default country for the bot.

        Parameters:
        - ctx: Command context.
        - args: Country to set as default.

        Returns:
        - None
        """
        country = " ".join(args)
        if not utils.validate_country(country):
            await ctx.send("Invalid country.")
            return
        self.default_country = utils.format_country_display(country)
        await ctx.send(f"Default country set to {self.default_country}.")

    @commands.command(
        name="set-language", help="Sets the bot language.", aliases=["sl"]
    )
    async def set_language(self, ctx, language_code):
        """
        Command to set the language of the bot.

        Parameters:
        - ctx: Command context.
        - language_code: Language code to set.

        Returns:
        - None
        """
        if not utils.validate_language(language_code):
            await ctx.send("Idioma no válido.")
            return
        self.language = language_code
        await ctx.send(f"Se cambió el idioma a {self.language}.")

    @commands.command(
        name="languages", help="Shows available languages.", aliases=["langs"]
    )
    async def show_languages(self, ctx):
        """
        Command to show available languages.

        Parameters:
        - ctx: Command context.

        Returns:
        - None
        """
        embed = discord.Embed(
            title=f'{utils.translate(self.language, "AvailableLanguages")}',
            color=discord.Color.random(),
        )
        languages = utils.load_languages()
        for lang, code in languages.items():
            embed.add_field(name="", value=f"- **{lang} ({code})**", inline=False)
        await ctx.send(embed=embed)

    @tasks.loop(hours=2)
    async def check_new_competitions(self):
        """
        Function to check for new competitions every 2 hours.
        """
        db.delete_old_competitions()

        if self.channel:
            print("Checking for new competitions...")
            current_comps = utils.fetch_tournaments(utils.URL, self.default_country)
            for comp in current_comps:
                comp["Start Date"] = comp["Start Date"].strftime("%Y-%m-%d")
                comp["End Date"] = comp["End Date"].strftime("%Y-%m-%d")

            known_comps = db.load_known_competitions()
            known_urls = {comp["URL"] for comp in known_comps}
            new_comps = [
                comp for comp in current_comps if comp["URL"] not in known_urls
            ]

            if new_comps:
                print("New competitions found.")
                view = PaginationView(new_comps, self.default_country, self.language)
                mention = f':tada: **@everyone, {utils.translate(self.language, "NewCompetitions")}** :tada:\n\n'
                embeds = view.create_notification_embed(new_comps)

                for comp in new_comps:
                    db.save_competition(comp)

                await self.channel.send(mention, embeds=embeds)

            else:
                print("No new competitions found.")

    @commands.command(
        name="competitions",
        help="Displays current competitions for the specified country.",
        aliases=["comps"],
    )
    async def competitions(self, ctx, *args):
        country = " ".join(args) if args else self.default_country
        competitions = utils.fetch_tournaments(utils.URL, country)

        view = PaginationView(competitions, country, self.language)
        view.translate_buttons()
        await view.send(ctx)


class PaginationView(discord.ui.View):
    def __init__(self, competitions, country="Chile", language="es"):
        super().__init__()
        self.language = language
        self.current_page = 1
        self.per_page = 3
        self.competitions = competitions
        self.country = country
        self.update_button_states()

    def update_button_states(self):
        total_pages = (len(self.competitions) + self.per_page - 1) // self.per_page
        self.first_page.disabled = self.current_page == 1
        self.previous.disabled = self.current_page == 1
        self.next.disabled = self.current_page == total_pages
        self.last_page.disabled = self.current_page == total_pages

    def translate_buttons(self):
        """
        Translates button labels for pagination controls.
        """
        self.first_page.label = utils.translate(self.language, "First")
        self.previous.label = utils.translate(self.language, "Previous")
        self.next.label = utils.translate(self.language, "Next")
        self.last_page.label = utils.translate(self.language, "Last")

    async def send(self, ctx):
        """
        Sends the initial pagination view message.

        Parameters:
        - ctx: Command context.

        Returns:
        - None
        """
        # Llamar al método de traducción
        self.translate_buttons()

        # Enviar el primer conjunto de competiciones como embed
        initial_competitions = self.competitions[: self.per_page]
        embed = self.create_competition_embed(initial_competitions)

        # Enviar el mensaje inicial con la vista de botones
        self.message = await ctx.send(embed=embed, view=self)

    def create_notification_embed(self, competitions):
        """
        Creates embeds for new competitions notification.

        Parameters:
        - competitions (list): List of new competitions.

        Returns:
        - list: List of discord.Embed objects.
        """
        embeds = []
        for comp in competitions:
            embed = discord.Embed(color=discord.Color.blue())
            embed.set_thumbnail(url="https://i.imgur.com/yscsmKO.jpeg")
            embed.set_footer(
                text="WCA Notifier Bot", icon_url="https://i.imgur.com/yscsmKO.jpeg"
            )
            embed.add_field(name=comp["Name"], value=comp["URL"], inline=False)
            embed.add_field(name="Location", value=comp["Location"], inline=True)
            if comp["Start Date"] == comp["End Date"]:
                embed.add_field(name="Date", value=comp["Start Date"], inline=True)
            else:
                embed.add_field(
                    name="Start Date", value=comp["Start Date"], inline=True
                )
                embed.add_field(name="End Date", value=comp["End Date"], inline=True)
            embeds.append(embed)
        return embeds

    async def update_competitions(self, competitions):
        """
        Updates the message with the current page of competitions.

        Parameters:
        - competitions (list): List of competitions for the current page.

        Returns:
        - None
        """
        embed = self.create_competition_embed(competitions)
        await self.message.edit(embed=embed, view=self)

    def create_competition_embed(self, competitions):
        """
        Creates an embed for displaying a page of competitions.

        Parameters:
        - competitions (list): List of competitions for the current page.

        Returns:
        - discord.Embed: The created embed.
        """
        embed = discord.Embed(
            title=f":trophy: {utils.translate(self.language, 'CurrentCompetitions')} {self.country} :trophy:",
            color=discord.Color.blue(),
        )
        embed.set_footer(
            text="WCA Notifier Bot", icon_url="https://i.imgur.com/yscsmKO.jpeg"
        )

        if not competitions:
            embed.add_field(
                name="No competitions found",
                value="No upcoming competitions available.",
                inline=False,
            )
            return embed

        for i, comp in enumerate(competitions):
            # Format dates
            start_date = comp["Start Date"].strftime("%d/%m/%Y")
            end_date = comp["End Date"].strftime("%d/%m/%Y")

            # Add competition name and link
            embed.add_field(
                name=comp["Name"], value=f"[Link]({comp['URL']})", inline=False
            )

            # Add location with icon and translated label
            embed.add_field(
                name=":world_map: " + f"{utils.translate(self.language, 'Location')}",
                value=comp["Location"],
                inline=True,
            )

            # Check if start and end dates are the same
            if comp["Start Date"] == comp["End Date"]:
                embed.add_field(
                    name=":calendar: " + f"{utils.translate(self.language, 'Date')}",
                    value=start_date,
                    inline=True,
                )
            else:
                embed.add_field(
                    name=":calendar: "
                    + f"{utils.translate(self.language, 'StartDate')}",
                    value=start_date,
                    inline=True,
                )
                embed.add_field(
                    name=":calendar: " + f"{utils.translate(self.language, 'EndDate')}",
                    value=end_date,
                    inline=True,
                )

            # Add separator for all but the last competition
            if i != len(competitions) - 1:
                embed.add_field(name="", value="\u200b", inline=False)

        return embed

    # Pagination button functions
    @discord.ui.button(label="First", style=discord.ButtonStyle.primary, emoji="⏮️")
    async def first_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        self.current_page = 1
        self.update_button_states()  # Update button states
        await self.update_competitions(self.competitions[: self.per_page])

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        self.current_page -= 1
        self.update_button_states()  # Update button states
        end = self.current_page * self.per_page
        start = end - self.per_page
        await self.update_competitions(self.competitions[start:end])

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_page += 1
        self.update_button_states()  # Update button states
        end = self.current_page * self.per_page
        start = end - self.per_page
        await self.update_competitions(self.competitions[start:end])

    @discord.ui.button(label="Last", style=discord.ButtonStyle.primary, emoji="⏭️")
    async def last_page(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.defer()
        self.current_page = (
            len(self.competitions) + self.per_page - 1
        ) // self.per_page
        self.update_button_states()  # Update button states
        end = self.current_page * self.per_page
        start = end - self.per_page
        await self.update_competitions(self.competitions[start:])


async def setup(bot):
    await bot.add_cog(WCA(bot))
