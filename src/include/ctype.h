#ifndef H1_LIBC_CTYPE_H
#define H1_LIBC_CTYPE_H
static inline int isalpha(int v) { return (v>='A'&&v<='Z')||(v>='a'&&v<='z'); }
static inline int isalnum(int v) { return isalpha(v)||(v>='0'&&v<='9'); }

static inline int isdigit(int value)
{
    return value >= '0' && value <= '9';
}

static inline int isspace(int value)
{
    return value == ' ' || value == '\t' || value == '\n' ||
        value == '\r' || value == '\f' || value == '\v';
}

static inline int tolower(int value)
{
    return value >= 'A' && value <= 'Z' ? value + ('a' - 'A') : value;
}

static inline int toupper(int value)
{
    return value >= 'a' && value <= 'z' ? value - ('a' - 'A') : value;
}

#endif
