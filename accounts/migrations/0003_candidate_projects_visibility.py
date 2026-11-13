import django.db.models.deletion
from django.db import migrations, models


def migrate_legacy_projects(apps, schema_editor):
    CandidateProfile = apps.get_model("accounts", "CandidateProfile")
    CandidateProject = apps.get_model("accounts", "CandidateProject")

    for profile in CandidateProfile.objects.all().iterator():
        legacy_projects = profile.projects or []
        if not isinstance(legacy_projects, list):
            continue

        for index, project in enumerate(legacy_projects):
            if not isinstance(project, dict):
                continue
            technologies = project.get("technologies", project.get("tech_stack", [])) or []
            if isinstance(technologies, str):
                technologies = [item.strip() for item in technologies.split(",") if item.strip()]
            elif not isinstance(technologies, list):
                technologies = []
            CandidateProject.objects.create(
                profile_id=profile.pk,
                title=str(project.get("title", "Untitled project"))[:200],
                description=str(project.get("description", "")),
                technologies=technologies,
                github_url=project.get("github_url", project.get("github", "")) or "",
                live_demo_url=project.get("live_demo_url", project.get("demo_url", "")) or "",
                display_order=index,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_alter_auditlog_id_alter_candidateprofile_id_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidateprofile",
            name="is_public",
            field=models.BooleanField(
                default=False,
                help_text="Allow anyone with the portfolio link to view this profile.",
            ),
        ),
        migrations.CreateModel(
            name="CandidateProject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True)),
                ("technologies", models.JSONField(blank=True, default=list)),
                ("github_url", models.URLField(blank=True)),
                ("live_demo_url", models.URLField(blank=True)),
                ("image", models.ImageField(blank=True, null=True, upload_to="candidate_projects/")),
                ("featured", models.BooleanField(default=False)),
                ("display_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="candidate_projects", to="accounts.candidateprofile")),
            ],
            options={
                "ordering": ["-featured", "display_order", "-created_at"],
            },
        ),
        migrations.RunPython(migrate_legacy_projects, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="candidateproject",
            constraint=models.UniqueConstraint(
                condition=models.Q(featured=True),
                fields=("profile",),
                name="unique_featured_candidate_project",
            ),
        ),
        migrations.RemoveField(
            model_name="candidateprofile",
            name="projects",
        ),
    ]
