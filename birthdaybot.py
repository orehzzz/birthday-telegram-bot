import logging
import datetime
import traceback
import pytz
import configparser

from telegram import Bot, BotCommand
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
)
from telegram.ext import filters, Defaults


from peewee import (
    Model,
    PostgresqlDatabase,
    TextField,
    SmallIntegerField,
    CharField,
    ForeignKeyField,
)

logging.basicConfig(
    filename="birthdaybot_log.txt",
    level=logging.DEBUG,
    format=" %(asctime)s - %(levelname)s - %(message)s",
)

config = configparser.ConfigParser()
config.read("birthdaybot_config.ini")
CREATOR_ID = config["Bot"]["creator_id"]
BOT_TOKEN = config["Bot"]["bot_token"]

text_config = configparser.ConfigParser()
text_config.read(r"conf_en.ini")


psql_db = PostgresqlDatabase(
    config["Database"]["name"],
    user=config["Database"]["user"],
    password=config["Database"]["password"],
)


class BaseModel(Model):
    class Meta:
        database = psql_db


class User(BaseModel):
    col_creator = CharField()
    col_language = CharField(default="en")


class Birthdays(BaseModel):
    col_name = CharField()
    col_day = SmallIntegerField()
    col_month = SmallIntegerField()
    col_year = SmallIntegerField(null=True)
    col_note = TextField(null=True)
    col_creator = ForeignKeyField(User, backref="birthdays")


with psql_db:
    psql_db.create_tables([Birthdays, User])


defaults = Defaults(tzinfo=pytz.timezone("Europe/Kyiv"))

# updater = Updater(
#     BOT_TOKEN,
#     defaults=defaults,
# )
application = Application.builder().token("BOT_TOKEN").build()

commands = [
    BotCommand("list", "your added birthdays"),
    BotCommand("add_birthday", "adds a birthday to your list"),
    BotCommand("delete_birthday", "deletes a birthday from your list"),
    BotCommand("add_note", "add some info about someone"),
    BotCommand("help", "general info"),
    BotCommand("language", "change Bot's language"),
    BotCommand("stop", "to stop"),
]
bot = Bot(BOT_TOKEN)
bot.set_my_commands(commands)


ADD_NAME, ADD_DATE, ADD_NOTE, DEL_NAME, DESC_NAME, CHANGE_LANG = range(6)


async def help(update, context):
    await update.effective_message.reply_text(
        f"""
    {text(update, "Help", "head")}:
    /list - {text(update, "Help", "list")}
    /add_birthday - {text(update, "Help", "add_birthday")} 
    /delete_birthday - {text(update, "Help", "delete_birthday")}
    /add_note - {text(update, "Help", "add_note")}
    /langauge - {text(update, "Help", "language")}

    /help - {text(update, "Help", "help")}
    /stop - {text(update, "Help", "stop")}
    """
    )


async def reminder(context):#ContextTypes.DEFAULT_TYPE
    update = None
    when_remind_dict = {
        datetime.date.today() + datetime.timedelta(days=7): "week",
        datetime.date.today() + datetime.timedelta(days=1): "tomorrow",
        datetime.date.today(): "today",
    }
    for when_remind in when_remind_dict:
        for birthday in Birthdays.select().where(
            (Birthdays.col_day == when_remind.day)
            & (Birthdays.col_month == when_remind.month)
        ):
            lang = User.get(User.id == birthday.col_creator).col_language
            name = birthday.col_name
            note = birthday.col_note
            message = text(update, "Reminder", "message_start", lang=lang).format(
                name=name,
                when=text(update, "Reminder", when_remind_dict[when_remind], lang=lang),
            )
            if birthday.col_year:
                age = when_remind.year - birthday.col_year
                message += text(update, "Reminder", "message_age", lang=lang).format(
                    age=age
                )
            if note:
                message += "\n" + text(
                    update, "Reminder", "message_note", lang=lang
                ).format(note=note)
            message += "\n" + text(update, "Reminder", "message_end", lang=lang)
            await context.bot.send_message(
                chat_id=User.get(User.id == birthday.col_creator).col_creator,
                text=message,
            )


def text(update, section, key, lang=None):
    if not lang:
        lang = User.get(User.col_creator == update.effective_user.id).col_language
    text_config.read(f"conf_{lang}.ini")
    return text_config[section][key]


async def language(update, context):
    keyboard = [
        [
            InlineKeyboardButton("English", callback_data="en"),
            InlineKeyboardButton("Українська", callback_data="ua"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        text(update, "Language", "choose"), reply_markup=reply_markup
    )
    return CHANGE_LANG


async def _change_language(update, context):
    answer = update.callback_query.data
    User.update(col_language=answer).where(
        User.col_creator == update.effective_user.id
    ).execute()
    text_config.read(f"conf_{answer}.ini")
    await update.callback_query.edit_message_text(
        text=text(update, "Language", "changed")
    )
    help(update, context)
    return ConversationHandler.END


async def add_birthday(
    update, context
):  # change function names to add_1, add_2 or similar
    await update.message.reply_text(text(update, "AddBirthday", "print_name"))
    return ADD_NAME


async def _add_name(update, context):
    name = update.message.text
    user = User.select().where(User.col_creator == update.effective_user.id).first()
    if len(name) > 255:
        await update.message.reply_text(text(update, "AddBirthday", "too_long"))
        return ADD_NAME
    if user.birthdays.select().where(Birthdays.col_name == name).first():
        await update.message.reply_text(text(update, "AddBirthday", "already_taken"))
        return ADD_NAME
    context.user_data["current_name"] = name
    await update.message.reply_text(text(update, "AddBirthday", "print_date"))
    return ADD_DATE


async def _save_birthday(update, context):
    date = update.message.text
    try:
        if not date[2] == ".":
            raise ValueError
        day, month = int(date[:2]), int(date[3:5])
        if day == 29 and month == 2:
            await update.message.reply_text(
                text(update, "AddBirthday", "29th").format(newline1="\n", newline2="\n")
            )
            return ADD_DATE
        year = None
        if len(date) == 10:
            if not date[5] == ".":
                raise ValueError
            year = int(date[-4:])
            if datetime.date.today() < datetime.date(year, month, day):
                raise ValueError
        datetime.date(datetime.date.today().year, month, day)
    except Exception:
        await update.message.reply_text(text(update, "AddBirthday", "invalid_date"))
        return ADD_DATE
    Birthdays.create(
        col_name=context.user_data["current_name"],
        col_day=day,
        col_month=month,
        col_year=year,
        col_creator=User.get(User.col_creator == update.effective_user.id),
    )
    await update.message.reply_text(text(update, "AddBirthday", "added"))
    help(update, context)
    return ConversationHandler.END


async def add_note(update, context):
    await update.message.reply_text(text(update, "AddNote", "print_name"))
    list(update, context)
    return DESC_NAME


async def _find_name(update, context):
    name = update.message.text
    user = User.select().where(User.col_creator == update.effective_user.id).first()
    if not user.birthdays.select().where(Birthdays.col_name == name):
        await update.message.reply_text(text(update, "AddNote", "invalid_name"))
        return DESC_NAME
    context.user_data["current_name"] = name
    await update.message.reply_text(
        text(update, "AddNote", "print_desc").format(newline="\n")
    )
    return ADD_NOTE


async def _save_note(update, context):
    note = update.message.text
    user = User.select().where(User.col_creator == update.effective_user.id).first()
    Birthdays.update(col_note=note).where(
        (Birthdays.col_name == context.user_data["current_name"])
        & (Birthdays.col_creator == user.id)
    ).execute()
    await update.message.reply_text(text(update, "AddNote", "added"))
    help(update, context)
    return ConversationHandler.END


async def delete_birthday(update, context):
    list(update, context)
    await update.message.reply_text(text(update, "DeleteBirthday", "print_name"))
    return DEL_NAME


async def _del_name(update, context):
    del_name = update.message.text
    user = User.select().where(User.col_creator == update.effective_user.id).first()
    query = Birthdays.delete().where(
        (Birthdays.col_creator == user) & (Birthdays.col_name == del_name)
    )
    if not await query.execute():
        await update.message.reply_text(text(update, "DeleteBirthday", "invalid_name"))
        return DEL_NAME
    await update.message.reply_text(text(update, "DeleteBirthday", "deleted"))
    help(update, context)
    return ConversationHandler.END


async def list(update, context):
    message = text(update, "List", "head") + "\n"
    border = "=" * 30
    today = datetime.date.today()
    today_added = 0

    user = (
        User.select()
        .where(User.col_creator == update.effective_user.id)
        .first()
        .birthdays
    )

    for birthday in user.select().order_by(Birthdays.col_month, Birthdays.col_day):
        name, note = birthday.col_name, birthday.col_note
        day, month, year = (
            str(birthday.col_day),
            text(update, "Month", str(birthday.col_month)),
            str(birthday.col_year),
        )

        if datetime.date(today.year, birthday.col_month, int(day)) == today:
            today_birthday = text(update, "List", "today_birthday").format(name=name)
            message += f"{border}\n{day} {month} --- {today_birthday}\n{border}\n"
            today_added = 1
            continue
        elif (
            datetime.date(today.year, birthday.col_month, int(day)) > today
            and not today_added
        ):
            word_today = text(update, "List", "today")
            today_month = text(update, "Month", str(today.month))
            message += (
                f"{border}\n{today.day} {today_month} --- {word_today}\n{border}\n"
            )
            today_added = 1
        space = "-"
        if len(name) < 9:
            space = "-" * (10 - len(name))
        message += f"{day} {month}"
        if birthday.col_year:
            message += f", {year}"
        message += f"  {space}  {name}"
        if note:
            message += f" ({note})\n"
        else:
            message += f"\n"

    if message == text(update, "List", "head"):
        await update.message.reply_text(
            text(update, "List", "empty").format(newline="\n")
        )
    else:
        if today_added == 0:
            today_month = text(update, "Month", str(today.month))
            word_today = text(update, "List", "today")
            message += (
                f"{border}\n{today.day} {today_month} --- {word_today}\n{border}\n"
            )
        await update.message.reply_text(message)


async def stop(update, context):
    return ConversationHandler.END


async def start(update, context):
    if not User.select().where(User.col_creator == update.effective_user.id):
        User.create(col_creator=update.effective_user.id)
    await update.message.reply_text(text(update, "Misc", "start"))
    help(update, context)


add = ConversationHandler(
    entry_points=[CommandHandler("add_birthday", add_birthday)],
    states={
        ADD_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), _add_name)],
        ADD_DATE: [MessageHandler(filters.TEXT & (~filters.COMMAND), _save_birthday)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
)

delete = ConversationHandler(
    entry_points=[CommandHandler("delete_birthday", delete_birthday)],
    states={
        DEL_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), _del_name)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
)

describe = ConversationHandler(
    entry_points=[CommandHandler("add_note", add_note)],
    states={
        DESC_NAME: [MessageHandler(filters.TEXT & (~filters.COMMAND), _find_name)],
        ADD_NOTE: [MessageHandler(filters.TEXT & (~filters.COMMAND), _save_note)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, stop),
    ],
)


async def error_handler(update, context):
    exc_info = context.error

    error_traceback = traceback.format_exception(
        type(exc_info), exc_info, exc_info.__traceback__
    )

    message = (
        "<i>bot_data</i>\n"
        f"<pre>{context.bot_data}</pre>\n"
        "<i>user_data</i>\n"
        f"<pre>{context.user_data}</pre>\n"
        "<i>chat_data</i>\n"
        f"<pre>{context.chat_data}</pre>\n"
        "<i>exception</i>\n"
        f"<pre>{''.join(error_traceback)}</pre>"
    )

    await context.bot.send_message(chat_id=CREATOR_ID, text=message, parse_mode="HTML")
    await update.effective_user.send_message(text(update, "Misc", "error"))


application.add_error_handler(error_handler)
application.add_handler(CommandHandler("help", help), 0)
application.add_handler(CommandHandler("list", list), 0)
application.add_handler(CommandHandler("start", start, 0))
application.add_handler(CommandHandler("stop", stop), 0)
application.add_handler(CommandHandler("language", language), 1)
application.add_handler(
    CallbackQueryHandler(_change_language, pattern="ua|en"),
    0,
)
application.add_handler(add, 2)
application.add_handler(delete, 3)
application.add_handler(describe, 4)
# application.add_handler(CommandHandler('start', start_callback))


application.job_queue.run_daily(
    reminder, time=datetime.time(hour=9, minute=0, second=0)
)

application.run_polling()
# updater.idle()
