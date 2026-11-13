from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import AuditLog, CandidateProfile, CandidateProject, Company, User


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Password confirmation", widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "role", "company")

    def clean_password2(self):
        p1, p2 = self.cleaned_data.get("password1"), self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    add_form = UserCreateForm
    ordering = ["email"]
    list_display = ["email", "first_name", "last_name", "role", "company", "is_active"]
    list_filter = ["role", "is_active", "company"]
    search_fields = ["email", "first_name", "last_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("first_name", "last_name", "phone", "designation", "avatar")}),
        ("Organisation", {"fields": ("role", "company")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "role", "company", "password1", "password2")}),
    )


admin.site.register(Company)
admin.site.register(CandidateProfile)
admin.site.register(CandidateProject)
admin.site.register(AuditLog)
