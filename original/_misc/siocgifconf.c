#include <arpa/inet.h>
#include <net/if.h>
#include <netinet/in.h>
#include <netinet/ip.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main()
{
    struct ifreq ifrs[20] = {};
    struct ifconf ifc = {
        .ifc_len = sizeof(ifrs),
        .ifc_req = ifrs,
    };
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (sock == -1) {
        perror("socket");
        return 1;
    }
    int ret = ioctl(sock, SIOCGIFCONF, &ifc);
    if (ret == -1) {
        perror("ioctl");
        return 1;
    } else if (ret != 0) {
        fprintf(stderr, "ioctl returned %d\n", ret);
    }
    for (int i = 0; i < ifc.ifc_len / sizeof(*ifrs); ++i) {
        struct ifreq *ifr = &ifrs[i];
        // TODO where is the constant for maximum possible name length?!
        char host[INET6_ADDRSTRLEN] = {};
        void const *src = NULL;
        // TODO is this really necessary? inet_ntop should be family-agnostic
        switch (ifr->ifr_addr.sa_family) {
        case AF_INET:
            src = &((struct sockaddr_in *)&ifr->ifr_addr)->sin_addr;
            break;
        case AF_INET6:
            src = &((struct sockaddr_in6 *)&ifr->ifr_addr)->sin6_addr;
            break;
        default:
            fprintf(stderr, "Unhandled socket family\n");
            return 1;
        }
        if (!inet_ntop(ifr->ifr_addr.sa_family, src, host, sizeof(host))) {
            perror("inet_ntop");
            return 1;
        }
        printf("%.*s: %s\n", IFNAMSIZ, ifr->ifr_name, host);
    }
    return 0;
}
