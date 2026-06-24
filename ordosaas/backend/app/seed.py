"""
Script de seed pour l'environnement de demonstration.
Usage : python -m app.seed
"""
import asyncio
import os

from sqlalchemy import select

from app.auth.utils import hash_password
from app.database import AsyncSessionLocal, init_db
from app.instances.service import import_instance
from app.models.instance import ProblemInstance
from app.models.machine import Machine
from app.models.tenant import Tenant
from app.models.user import User

DEMO_TENANT_SLUG = "ensias-demo"
DEMO_ADMIN_EMAIL = "admin@ensias-demo.ma"
DEMO_ADMIN_PASSWORD = "demo_password"

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")

DEMO_MACHINES = [
    ("M1", "Tour CNC"),
    ("M2", "Fraiseuse"),
    ("M3", "Centre d'usinage"),
]


def _read(name):
    path = os.path.join(FIXTURES_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


async def main():
    await init_db()

    async with AsyncSessionLocal() as db:
        # 1. Tenant
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == DEMO_TENANT_SLUG))
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(name="ENSIAS Demo", slug=DEMO_TENANT_SLUG)
            db.add(tenant)
            await db.flush()
            print("[seed] tenant ENSIAS Demo cree")

        # 2. Admin
        admin = (
            await db.execute(
                select(User).where(User.tenant_id == tenant.id, User.email == DEMO_ADMIN_EMAIL)
            )
        ).scalar_one_or_none()
        if admin is None:
            admin = User(
                tenant_id=tenant.id, email=DEMO_ADMIN_EMAIL,
                password_hash=hash_password(DEMO_ADMIN_PASSWORD),
                first_name="Admin", last_name="ENSIAS", role="admin", status="active",
            )
            db.add(admin)
            await db.flush()
            print(f"[seed] admin {DEMO_ADMIN_EMAIL} cree (mdp: {DEMO_ADMIN_PASSWORD})")

        # 3. Machines — IMPERATIF : creees et committees AVANT l'import de
        # l'instance, sinon la validation CSV echoue (machine_id inexistant).
        for ext, name in DEMO_MACHINES:
            exists = (
                await db.execute(
                    select(Machine).where(
                        Machine.tenant_id == tenant.id, Machine.external_id == ext
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(Machine(tenant_id=tenant.id, external_id=ext, name=name, status="active"))
                print(f"[seed] machine {ext} ({name}) creee")
        await db.commit()

        # Verifie que toutes les machines requises existent bien avant l'import.
        existing_machines = {
            m.external_id
            for m in (
                await db.execute(select(Machine).where(Machine.tenant_id == tenant.id))
            ).scalars().all()
        }
        required = {ext for ext, _ in DEMO_MACHINES}
        missing = required - existing_machines
        if missing:
            print(f"[seed] ERREUR : machines manquantes {missing}, import annule")
            return

        # 4. Import de l'instance exemple
        jobs_csv = _read("jobs.csv")
        ops_csv = _read("operations.csv")
        setups_csv = _read("setups.csv")
        if jobs_csv and ops_csv:
            already = (
                await db.execute(
                    select(ProblemInstance).where(ProblemInstance.tenant_id == tenant.id)
                )
            ).first()
            if already is None:
                # The fixture references M1..M3 which all exist as demo machines.
                imported = await import_instance(
                    "Instance exemple ENSIAS", "Instance de demonstration (10 jobs, 3 machines)",
                    jobs_csv, ops_csv, setups_csv, tenant.id, admin.id, db,
                )
                print(f"[seed] instance importee : {imported.id} ({imported.nb_jobs} jobs)")
            else:
                print("[seed] une instance existe deja, import ignore")
        else:
            print("[seed] fixtures CSV absentes, import ignore")

    print("[seed] Seed completed")


if __name__ == "__main__":
    asyncio.run(main())
