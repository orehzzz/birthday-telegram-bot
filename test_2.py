import datetime
import traceback
import calendar
import pytz

from peewee import (
    Model,
    PostgresqlDatabase,
    TextField,
    SmallIntegerField,
    # IntegerField,
    CharField,
    # DateField,
)
from telegram.bot import Bot, BotCommand
from telegram.ext.callbackcontext import CallbackContext
from telegram.ext import Filters, Defaults
from telegram.ext.commandhandler import CommandHandler
from telegram.ext.conversationhandler import ConversationHandler
from telegram.ext.messagehandler import MessageHandler
from telegram.ext.updater import Updater

# from telegram.ext.jobqueue import JobQueue

psql_db = PostgresqlDatabase("birthdays", user="postgres", password="l9999l")


class BaseModel(Model):
    class Meta:
        database = psql_db


class User(BaseModel):
    col_name = CharField()
    col_day = SmallIntegerField()
    col_month = SmallIntegerField()
    col_year = SmallIntegerField(null=True)
    # col_date = DateField()
    col_note = TextField(null=True)
    col_creator = CharField()


with psql_db:
    # psql_db.drop_tables([User])
    psql_db.create_tables([User])

defaults = Defaults(tzinfo=pytz.timezone("Europe/Kyiv"))

updater = Updater(
    "5749842477:AAE72SsmVUNh0hFhy5KwTgnICe0m_zEqTyU",
    use_context=True,
    defaults=defaults,
)


commands = [
    BotCommand("list", "your added birthdays"),
    BotCommand("add_birthday", "adds a birthday to your list"),
    BotCommand("delete_birthday", "deletes a birthday from your list"),
    BotCommand("add_note", "add some info about someone"),
    BotCommand("help", "list of commands"),
    BotCommand("exit", "to stop"),
]
bot = Bot("5749842477:AAE72SsmVUNh0hFhy5KwTgnICe0m_zEqTyU")
bot.set_my_commands(commands)


NAME, DATE, NOTE = range(3)
CREATOR_ID = 651472384


def help(update, context):
    update.message.reply_text(
        """
        Commands to use:
    /list
    /add_birthday
    /delete_birthday
    /add_note

    /help
    /exit
    """
    )


def today_in_list(context):
    today = datetime.date.today()
    User.update(
        {
            User.col_day: today.day,
            User.col_month: today.month,
            User.col_year: today.year,
        }
    ).where(
        User.col_name == User.col_note == "**Today**" & User.col_creator == CREATOR_ID
    )


def reminder(context: CallbackContext):
    when_remind_list = {
        datetime.date.today() + datetime.timedelta(days=7): "in a week",
        datetime.date.today() + datetime.timedelta(days=1): "tomorrow",
        datetime.date.today(): "today!",
    }
    for when_remind in when_remind_list:
        for user in User.select().where(
            (User.col_day == when_remind.day) & (User.col_month == when_remind.month)
        ):
            name = user.col_name
            note = user.col_note
            day = str(user.col_day)
            month = str(user.col_month)
            message = f"Hi there. It is {name}'s birthday {when_remind_list[when_remind]} - {day}.{month}!\n"
            if user.col_year:
                age = when_remind.year - user.col_year
                message += f"He/She is turning {age}\n"
            if note:
                message += (
                    f" (Here is a note you left previously about {name}: {note})\n"
                )
            message += f"I hope you didn't forget? :)"

            context.bot.send_message(chat_id=user.col_creator, text=message)


def add_birthday(update, context):
    update.message.reply_text("Print person's name:")
    return NAME


def _add_name(update, context):
    name = update.message.text
    if len(name) > 255:
        update.message.reply_text("This name is too long. Choose another one:")
        return NAME
    elif (
        User.select(User.col_name)
        .where(
            (User.col_creator == update.effective_user.id) and (User.col_name == name)
        )
        .first()
    ):
        print(User.col_creator)
        update.message.reply_text("This name is already taken. Choose another one:")
        return NAME
    context.user_data["current_name"] = name
    update.message.reply_text("Great! Print a date (example:02.02.2002 or 02.02):")
    return DATE


def _save_birthday(update, context):
    date = update.message.text
    try:
        month, day = int(date[3:5]), int(date[:2])
        datetime.date(datetime.date.today().year, month, day)
        year = None
        if len(date) == 10:
            year = int(date[-4:])
            if datetime.date.today() < datetime.date(year, month, day):
                update.message.reply_text("This is a future date. Choose another one:")
                return DATE
    except ValueError:
        update.message.reply_text("This is an invalid date. Choose another one:")
        return DATE

    User.create(
        col_name=context.user_data["current_name"],
        col_day=day,
        col_month=month,
        col_year=year,
        col_creator=update.effective_user.id,
    )

    update.message.reply_text("Successfully added!")
    help(update, context)
    return ConversationHandler.END


def add_note(update, context):
    update.message.reply_text("About whom you want to add a note?(print a name)")
    list(update, context)
    return NAME


def _find_name(update, context):

    name = update.message.text
    context.user_data["current_name"] = name
    update.message.reply_text(
        """
    Print a description:
    (it could be a hint for a present or some notes for the future, etc.)
    """
    )
    return NOTE


def _save_note(update, context):
    note = update.message.text
    User.update(col_note=note).where(
        User.col_name == context.user_data["current_name"]
    ).execute()
    update.message.reply_text("Successfully added!")
    help(update, context)
    return ConversationHandler.END


def delete_birthday(update, context):
    list(update, context)
    update.message.reply_text("Which one to delete?(print a name)")
    return NAME


def _del_name(update, context):
    del_name = update.message.text
    User.delete().where(User.col_name == del_name).execute()
    update.message.reply_text("Successfully deleted!")
    help(update, context)
    return ConversationHandler.END


def list(update, context):
    message = "Your list of birthdays:\n"
    border = "=" * 30
    today = datetime.date.today()
    today_added = 0
    for user in (
        User.select()
        .where(User.col_creator == str(update.effective_user.id))
        .order_by(User.col_month, User.col_day)
    ):
        name, note = user.col_name, user.col_note
        day, month, year = (
            str(user.col_day),
            calendar.month_name[user.col_month],
            str(user.col_year),
        )
        if datetime.date(today.year, user.col_month, int(day)) == today:
            message += (
                f"{border}\n{day} {month} --- today is {name}'s birthday!\n{border}\n"
            )
            today_added = 1
            continue
        elif (
            datetime.date(today.year, user.col_month, int(day)) > today
            and not today_added
        ):
            message += f"{border}\n{today.day} {calendar.month_name[today.month]} --- today\n{border}\n"
            today_added = 1
        space = "-"
        if len(name) < 9:
            space = "-" * (10 - len(name))
        message += f"{day} {month}"
        if user.col_year:
            message += f", {year}"
        message += f"  {space}  {name}"
        if note:
            message += f" ({note})\n"
        else:
            message += f"\n"

    if message == "Your list of birthdays:\n":
        update.message.reply_text(
            "Your list is empty for now\nAdd some birthdays to your list with /add_birthday command"
        )
    else:
        if today_added == 0:
            message += f"{border}\n{today.day} {calendar.month_name[today.month]} --- today\n{border}\n"
        update.message.reply_text(message)


def exit(update, context):
    update.message.reply_text("stopped")
    return ConversationHandler.END


def start(update, context):
    update.message.reply_text("Hi")
    help(update, context)


add = ConversationHandler(
    entry_points=[CommandHandler("add_birthday", add_birthday)],
    states={
        NAME: [MessageHandler(Filters.text & (~Filters.command), _add_name)],
        DATE: [MessageHandler(Filters.text & (~Filters.command), _save_birthday)],
    },
    fallbacks=[CommandHandler("exit", exit)],
)

delete = ConversationHandler(
    entry_points=[CommandHandler("delete_birthday", delete_birthday)],
    states={
        NAME: [MessageHandler(Filters.text & (~Filters.command), _del_name)],
    },
    fallbacks=[
        CommandHandler("exit", exit),
    ],
)

describe = ConversationHandler(
    entry_points=[CommandHandler("add_note", add_note)],
    states={
        NAME: [MessageHandler(Filters.text & (~Filters.command), _find_name)],
        NOTE: [MessageHandler(Filters.text & (~Filters.command), _save_note)],
    },
    fallbacks=[
        CommandHandler("exit", exit),
    ],
)


def error_handler(update, context):
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

    context.bot.send_message(
        chat_id=651472384, text=message, parse_mode="HTML"
    )  # orehzzz's id - 651472384

    update.effective_user.send_message(
        "Something went wrong. Report was sent to @orehzzz"
    )


updater.dispatcher.add_error_handler(error_handler)
updater.dispatcher.add_handler(CommandHandler("help", help))
updater.dispatcher.add_handler(CommandHandler("list", list))
updater.dispatcher.add_handler(CommandHandler("start", start))
updater.dispatcher.add_handler(add)
updater.dispatcher.add_handler(delete)
updater.dispatcher.add_handler(describe)


updater.job_queue.run_daily(
    today_in_list, time=datetime.time(hour=0, minute=0, second=0)
)
updater.job_queue.run_daily(reminder, time=datetime.time(hour=10, minute=0, second=0))


updater.start_polling()
updater.idle()