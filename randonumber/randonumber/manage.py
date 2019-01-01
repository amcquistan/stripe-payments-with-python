from flask_script import Manager  
from flask_migrate import Migrate, MigrateCommand

from server import os, app, db, User, Purchase, Number

migrate = Migrate(app, db)  
manager = Manager(app)

# provide a migration utility command
manager.add_command('db', MigrateCommand)

# Python interpreter shell with application context
@manager.shell
def shell_ctx():  
    return dict(app=app,
                db=db,
                User=User,
                Purchase=Purchase,
                Number=Number)

if __name__ == '__main__':  
    manager.run()
