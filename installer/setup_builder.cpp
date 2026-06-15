/**
 * NEXORA Setup Launcher v2.0
 * Lance l'installateur Inno Setup en silence
 * Compile avec : g++ -o nexora_setup_launcher.exe setup_builder.cpp
 *                -mwindows -static -lshlwapi
 */

#include <windows.h>
#include <string>
#include <shlobj.h>

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow) {

    // Verifier les droits administrateur
    BOOL isAdmin = FALSE;
    PSID adminGroup = NULL;
    SID_IDENTIFIER_AUTHORITY ntAuthority = SECURITY_NT_AUTHORITY;

    if (AllocateAndInitializeSid(&ntAuthority, 2,
        SECURITY_BUILTIN_DOMAIN_RID, DOMAIN_ALIAS_RID_ADMINS,
        0, 0, 0, 0, 0, 0, &adminGroup)) {
        CheckTokenMembership(NULL, adminGroup, &isAdmin);
        FreeSid(adminGroup);
    }

    if (!isAdmin) {
        // Relancer en tant qu'administrateur
        char szPath[MAX_PATH];
        GetModuleFileName(NULL, szPath, MAX_PATH);
        ShellExecute(NULL, "runas", szPath, NULL, NULL, SW_SHOWNORMAL);
        return 0;
    }

    // Message de bienvenue
    int result = MessageBox(NULL,
        "Bienvenue dans l'installation de NEXORA v2.0\n\n"
        "Editeur : Hamadou Youssouf -- GTC Bertoua, Cameroun\n\n"
        "Cliquez OK pour continuer l'installation.",
        "NEXORA v2.0 -- Installation",
        MB_OKCANCEL | MB_ICONINFORMATION);

    if (result != IDOK) return 0;

    // Trouver et lancer nexora_setup.exe (Inno Setup)
    char szDir[MAX_PATH];
    GetModuleFileName(NULL, szDir, MAX_PATH);
    std::string exePath(szDir);
    size_t pos = exePath.rfind('\\');
    if (pos != std::string::npos) exePath = exePath.substr(0, pos);

    std::string setupPath = exePath + "\\nexora_setup.exe";

    // Verifier que l'installateur existe
    if (GetFileAttributes(setupPath.c_str()) == INVALID_FILE_ATTRIBUTES) {
        MessageBox(NULL,
            "Fichier d'installation nexora_setup.exe introuvable.\n"
            "Assurez-vous que tous les fichiers sont presents.",
            "Erreur", MB_OK | MB_ICONERROR);
        return 1;
    }

    // Lancer l'installateur Inno Setup
    SHELLEXECUTEINFO sei = {0};
    sei.cbSize = sizeof(sei);
    sei.fMask  = SEE_MASK_NOCLOSEPROCESS;
    sei.hwnd   = NULL;
    sei.lpVerb = "runas";
    sei.lpFile = setupPath.c_str();
    sei.nShow  = SW_SHOWNORMAL;

    if (!ShellExecuteEx(&sei)) {
        MessageBox(NULL, "Impossible de lancer l'installation.",
                   "Erreur", MB_OK | MB_ICONERROR);
        return 1;
    }

    // Attendre la fin de l'installation
    if (sei.hProcess) {
        WaitForSingleObject(sei.hProcess, INFINITE);
        CloseHandle(sei.hProcess);
    }

    return 0;
}
