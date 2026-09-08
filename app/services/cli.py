import click

from app.extensions import db


def register_cli_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (dev convenience; use migrations in production)."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
    def create_admin(name, email, password):
        from app.models.user import User

        if User.query.filter_by(email=email).first():
            click.echo(f"A user with email {email} already exists.")
            return
        user = User(name=name, email=email, role="administrator", status="active")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Administrator account created for {email}.")
